# STD packages
import concurrent.futures
import json
import logging
import os
import re
import sys
import textwrap
from typing import Any, Dict, List, Set, Union, Optional
from demisto_sdk.commands.common.content import (Integration, Playbook,
                                                 ReleaseNote, Script,
                                                 path_to_pack_object)
# Third party packages
import docker
import docker.errors
from git import Repo
import requests.exceptions
import urllib3.exceptions
from wcmatch.pathlib import Path
from demisto_sdk.commands.common.content.objects.abstract_objects.general_object import GeneralObject
from demisto_sdk.commands.lint.lint_refactor.LintGlobalFacts import LintGlobalFacts, build_lint_global_facts
from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.common.content.objects.pack_objects.pack import Pack
from demisto_sdk.commands.common.content.content import Content
from demisto_sdk.commands.common.constants import (PACKS_PACK_META_FILE_NAME,
INTEGRATIONS_DIR,
                                                   TYPE_PWSH, TYPE_PYTHON,
                                                   DemistoException)
# Local packages
from demisto_sdk.commands.common.logger import Colors
from demisto_sdk.commands.common.tools import (find_file, find_type,
                                               get_content_path,
                                               get_file_displayed_name,
                                               get_json,
                                               is_external_repository,
                                               print_error, print_v,
                                               print_warning,
                                               is_pack_path,
                                               retrieve_file_ending)
from demisto_sdk.commands.lint.helpers import (EXIT_CODES, FAIL, PWSH_CHECKS,
                                               PY_CHCEKS,
                                               build_skipped_exit_code,
                                               generate_coverage_report,
                                               get_test_modules, validate_env)
from demisto_sdk.commands.lint.linter import Linter

logger = logging.getLogger('demisto-sdk')


class LintManager:
    """ LintManager used to activate lint command using Linters in a single or multi thread.

    Attributes:
        input_dirs(str): Directories to run lint on.
        git_only(bool): Perform lint and test only on changed packs by git.
        all_packs(bool): Whether to run on all packages.
        quiet(bool): Whether to output a quiet response.
        verbose(int): Whether to output a detailed response.
        prev_ver(str): Version to compare against in git, if specified.
        json_file_path(str): JSON file path.
    """

    def __init__(self, input_dirs: str, git_only: bool, all_packs: bool, quiet: bool, verbose: int, prev_ver: str,
                 json_file_path: str = ''):

        # Verbosity level
        self._verbose = False if quiet else verbose
        self._prev_ver = prev_ver
        self._all_packs = all_packs
        # Set 'git' to true if no packs have been specified, 'lint' should operate as 'lint -g'
        git_only = git_only or (not all_packs and not input_dirs)
        # Filter packages to lint and test check
        # Gather facts for manager
        self.lint_global_facts: LintGlobalFacts = build_lint_global_facts(self._verbose)
        if not self.lint_global_facts.content_repo and (all_packs or git_only):
            raise DemistoException('Could not find content repository and -a or -g have been supplied.')
        self._pkgs: List[Path] = self._get_packages(content_repo=self._facts["content_repo"],
                                                    input=input_dirs,
                                                    git=git_only,
                                                    all_packs=all_packs,
                                                    base_branch=self._prev_ver)
        if json_file_path:
            if os.path.isdir(json_file_path):
                json_file_path = os.path.join(json_file_path, 'lint_outputs.json')
        self.json_file_path = json_file_path
        self.linters_error_list: list = []

    def _get_packages(self, content_repo: Repo, input_dirs: str, git: bool, all_packs: bool, base_branch: str) \
            -> List[Path]:
        """ Get packages paths to run lint command.

        Args:
            content_repo(git.Repo): Content repository object.
            input(str): dir pack specified as argument.
            git(bool): Perform lint and test only on changed packs.
            all_packs(bool): Whether to run on all packages.
            base_branch (str): Name of the branch to run the diff on.

        Returns:
            List[Path]: Pkgs to run lint
        """
        if all_packs or git:
            all_packages: List[Union[Script, Integration]] = self._get_all_packages(content_repo.working_dir)
            all_packages_path_list: List[Path] = [package.path for package in all_packages]

            if git:
                packages_to_test = self._filter_changed_packages(content_repo=content_repo,
                                                                 pkgs=all_packages_path_list, base_branch=base_branch)
                for pkg in packages_to_test:
                    print_v(f"Found changed package {Colors.Fg.cyan}{pkg}{Colors.reset}", log_verbose=self._verbose)
        else:  # specific pack as input, -i flag has been used
            packages_to_test = [(self._get_all_packages(path_) if is_pack_path(path_) else Path(path_))
                                for path_ in input_dirs.split(',')]
            for item in input.split(','):
                is_pack = os.path.isdir(item) and os.path.exists(os.path.join(item, PACKS_PACK_META_FILE_NAME))
                if is_pack:
                    pkgs.extend(LintManager._get_all_packages(content_dir=item))
                else:
                    pkgs.append(Path(item))

        total_found = len(pkgs)
        if git:
            pkgs = self._filter_changed_packages(content_repo=content_repo,
                                                 pkgs=pkgs, base_branch=base_branch)
            for pkg in pkgs:
                print_v(f"Found changed package {Colors.Fg.cyan}{pkg}{Colors.reset}",
                        log_verbose=self._verbose)
        print(f"Execute lint and test on {Colors.Fg.cyan}{len(pkgs)}/{total_found}{Colors.reset} packages")

        return pkgs

    @staticmethod
    def _get_all_packages(content_dir: str) -> List[Union[Integration, Script]]:
        """Gets all integration, script in packages and packs inside the given 'content_dir' path.

        Returns:
            list: A list of integration, script and beta_integration names.
        """
        content_dir_path: Path = Path(content_dir)
        # Getting Integrations residing in the given content dir path.
        dir_packages: List[Union[Integration, Script]] = [Integration(file_path) for file_path in
                                                          content_dir_path.glob(
                                                              ['Integrations/*/', 'Packs/*/Integrations/*/'])]
        # Getting Scripts residing in the given content dir path.
        dir_scripts: List[Script] = [Script(file_path) for file_path in
                                     content_dir_path.glob(['Scripts/*/', 'Packs/*/Scripts/*/'])]

        # Handling a case where input to a package was given
        dir_name: str = os.path.basename(os.path.dirname(content_dir))
        if dir_name == INTEGRATIONS_DIR:


        # Union of scripts and integrations returned.
        return dir_packages + dir_scripts

    def _filter_changed_packages(self, content_repo: Repo, pkgs: List[Path], base_branch: str) -> List[Path]:
        """ Checks which packages had changes using git (working tree, index, diff between HEAD and master in them and should
        run on Lint.

        Args:
            pkgs(List[Path]): pkgs to check
            base_branch (str): Name of the branch to run the diff on.

        Returns:
            List[Path]: A list of names of packages that should run.
        """
        print_v(
            f'Comparing to {Colors.Fg.cyan}{content_repo.remote()}/{base_branch}{Colors.reset} using'
            f' branch {Colors.Fg.cyan} {content_repo.active_branch}{Colors.reset}', log_verbose=self._verbose)
        staged_files = {content_repo.working_dir / Path(item.b_path).parent for item in
                        content_repo.active_branch.commit.tree.diff(None, paths=pkgs)}
        if content_repo.active_branch == 'master':
            last_common_commit = content_repo.remote().refs.master.commit.parents[0]
        else:
            last_common_commit = content_repo.merge_base(content_repo.active_branch.commit,
                                                         f'{content_repo.remote()}/{base_branch}')
        changed_from_base = {content_repo.working_dir / Path(item.b_path).parent for item in
                             content_repo.active_branch.commit.tree.diff(last_common_commit, paths=pkgs)}
        all_changed = staged_files.union(changed_from_base)
        pkgs_to_check = all_changed.intersection(pkgs)

        return list(pkgs_to_check)
