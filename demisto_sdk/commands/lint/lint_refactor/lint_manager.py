import os
from typing import List, Set, Union
# STD python packages
import io
import logging
import os
import re
import shlex
import shutil
import sqlite3
import tarfile
import textwrap
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Dict, Generator, List, Optional, Union
# STD packages
import concurrent.futures
import json
import logging
import os
import re
import sys
import textwrap
from typing import Any, Dict, List, Set

# Third party packages
import docker
import docker.errors
import git
import requests.exceptions
import urllib3.exceptions
from wcmatch.pathlib import Path

from demisto_sdk.commands.common.constants import (PACKS_PACK_META_FILE_NAME,
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
                                               retrieve_file_ending)
from demisto_sdk.commands.lint.helpers import (EXIT_CODES, FAIL, PWSH_CHECKS,
                                               PY_CHCEKS,
                                               build_skipped_exit_code,
                                               generate_coverage_report,
                                               get_test_modules, validate_env)
from demisto_sdk.commands.lint.linter import Linter

# Third party packages
import coverage
import docker
import docker.errors
import git
import requests
from docker.models.containers import Container

# Local packages
from demisto_sdk.commands.common.constants import (TYPE_PWSH, TYPE_PYTHON,
                                                   DemistoException)
from demisto_sdk.commands.com
from git import Repo
from wcmatch.pathlib import Path
import click
from demisto_sdk.commands.common.constants import (INTEGRATIONS_DIR, SCRIPTS_DIR,
                                                   DemistoException)
from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.common.logger import Colors
from demisto_sdk.commands.common.tools import (print_v,
                                               print_warning)
from demisto_sdk.commands.lint.lint_refactor.lint_global_facts import LintGlobalFacts, build_lint_global_facts
from demisto_sdk.commands.lint.lint_refactor.linters.bandit import BanditLinter
from demisto_sdk.commands.lint.lint_refactor.linters.flake8_linter import Flake8Linter
from demisto_sdk.commands.lint.lint_refactor.linters.mypy_linter import MyPyLinter
from demisto_sdk.commands.lint.lint_refactor.linters.pwsh_analyze_linter import PowershellAnalyzeLinter
from demisto_sdk.commands.lint.lint_refactor.linters.pwsh_test_linter import PowershellTestLinter
from demisto_sdk.commands.lint.lint_refactor.linters.pylint_linter import PylintLinter
from demisto_sdk.commands.lint.lint_refactor.linters.pytest_linter import PytestLinter
from demisto_sdk.commands.lint.lint_refactor.linters.vulture_linter import VultureLinter
from demisto_sdk.commands.lint.lint_refactor.linters.xsoar_linter import XSOARLinter
from demisto_sdk.commands.lint.lint_refactor.linters.abstract_linters.base_linter import BaseLinter


class LintManager:
    ALL_LINTERS: List[BaseLinter] = [BanditLinter, Flake8Linter, MyPyLinter, PowershellAnalyzeLinter,
                                     PowershellTestLinter, PylintLinter, PytestLinter, VultureLinter, XSOARLinter]
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
                 docker_timeout: int, keep_container: bool, json_file_path: str = ''):

        # Verbosity level
        self._verbose = False if quiet else verbose
        self._prev_ver = prev_ver
        self._all_packs = all_packs
        # Set 'git' to true if no packs have been specified, 'lint' should operate as 'lint -g'
        git_only = git_only or (not all_packs and not input_dirs)
        # Gather facts for manager
        self.lint_global_facts: LintGlobalFacts = build_lint_global_facts(docker_timeout, keep_container, self._verbose)
        if not self.lint_global_facts.content_repo and (all_packs or git_only):
            raise DemistoException('Could not find content repository and -a or -g have been supplied.')
        self.packages: List[Union[Script, Integration]] = self._get_packages(
            content_repo=self.lint_global_facts.content_repo,
            input_dirs=input_dirs,
            git=git_only,
            base_branch=self._prev_ver)
        if json_file_path and os.path.isdir(json_file_path):
            json_file_path = os.path.join(json_file_path, 'lint_outputs.json')
        self.json_file_path = json_file_path
        self.linters_error_list: list = []

    def _get_packages(self, content_repo: Repo, input_dirs: str, git: bool, base_branch: str) \
            -> List[Union[Script, Integration]]:
        """
        Get packages paths to run lint command.

        Args:
            content_repo (Repo): Content repository object.
            input_dirs (str): dir pack specified as argument.
            git (bool): Perform lint and test only on changed packs.
            base_branch (str): Name of the branch to run the diff on.

        Returns:
            List[Union[Script, Integration]]: Packages to run lint.
        """
        if input_dirs:
            packages: List[Union[Script, Integration]] = []
            for package in input_dirs.split(','):
                # Should be either Integrations or Scripts
                integration_or_script_dir: str = os.path.basename(os.path.dirname(package))
                if integration_or_script_dir == INTEGRATIONS_DIR:
                    packages.append(Integration(package))
                if integration_or_script_dir == SCRIPTS_DIR:
                    packages.append(Script(package))
                else:
                    print_warning(f'Given input: {package} is not a package dir. Please supply inputs of integration or'
                                  f' script directory only. Skipping Lint for given path.')
        else:
            packages: List[Union[Script, Integration]] = self._get_all_packages(content_repo.working_dir)

        total_found = len(packages)
        if git:
            packages = self._filter_changed_packages(content_repo, packages, base_branch)

        click.secho(f'Execute lint and test on {Colors.Fg.cyan}{len(packages)}/{total_found}{Colors.reset} packages')

        return packages

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

        return dir_packages + dir_scripts

    def _filter_changed_packages(self, content_repo: Repo, packages: List[Union[Script, Integration]],
                                 base_branch: str) -> List[Union[Script, Integration]]:
        """ Checks which packages had changes using git (working tree, index, diff between HEAD and master in them
        and should run on Lint).

        Args:
            packages (List[Union[Script, Integration]): Packages to check.
            base_branch (str): Name of the branch to run the diff on.

        Returns:
            List[Path]: A list of names of packages that should run.
        """
        packages_paths: List[Path] = [package.path for package in packages]
        print_v(
            f'Comparing to {Colors.Fg.cyan}{content_repo.remote()}/{base_branch}{Colors.reset} using'
            f' branch {Colors.Fg.cyan} {content_repo.active_branch}{Colors.reset}', log_verbose=self._verbose)
        staged_files = {content_repo.working_dir / Path(item.b_path).parent for item in
                        content_repo.active_branch.commit.tree.diff(None, paths=packages_paths)}
        if content_repo.active_branch == 'master':
            last_common_commit = content_repo.remote().refs.master.commit.parents[0]
        else:
            last_common_commit = content_repo.merge_base(content_repo.active_branch.commit,
                                                         f'{content_repo.remote()}/{base_branch}')
        changed_from_base = {content_repo.working_dir / Path(item.b_path).parent for item in
                             content_repo.active_branch.commit.tree.diff(last_common_commit, paths=packages_paths)}
        all_changed = staged_files.union(changed_from_base)
        packages_to_check_path: Set[str] = all_changed.intersection(packages_paths)
        packages_filtered: List[Union[Script, Integration]] = [package for package in packages if
                                                               package.path in packages_to_check_path]
        for pkg in packages_filtered:
            print_v(f"Found changed package {Colors.Fg.cyan}{pkg}{Colors.reset}", log_verbose=self._verbose)
        return packages_filtered

    def get_linters(self, package: Union[Script, Integration]) -> List[BaseLinter]:
        return [linter for linter in self.ALL_LINTERS if linter.should_run()]

    @staticmethod
    def run_linters(linters: List[BaseLinter]):
        for linter in linters:
            linter.run()

    def run_dev_packages(self, parallel: int, no_flake8: bool, no_xsoar_linter: bool, no_bandit: bool, no_mypy: bool,
                         no_pylint: bool, no_coverage: bool, coverage_report: str,
                         no_vulture: bool, no_test: bool, no_pwsh_analyze: bool, no_pwsh_test: bool,
                         keep_container: bool,
                         test_xml: str, failure_report: str, docker_timeout: int) -> int:
        """ Runs the Lint command on all given packages.

        Args:
            parallel(int): Whether to run command on multiple threads
            no_flake8(bool): Whether to skip flake8
            no_xsoar_linter(bool): Whether to skip xsoar linter
            no_bandit(bool): Whether to skip bandit
            no_mypy(bool): Whether to skip mypy
            no_vulture(bool): Whether to skip vulture
            no_pylint(bool): Whether to skip pylint
            no_coverage(bool): Run pytest without coverage report
            coverage_report(str): the directory fo exporting the coverage data
            no_test(bool): Whether to skip pytest
            no_pwsh_analyze(bool): Whether to skip powershell code analyzing
            no_pwsh_test(bool): whether to skip powershell tests
            keep_container(bool): Whether to keep the test container
            test_xml(str): Path for saving pytest xml results
            failure_report(str): Path for store failed packs report
            docker_timeout(int): timeout for docker requests

        Returns:
            int: exit code by fail exit codes by var EXIT_CODES
        """
        lint_status: Dict = {
            "fail_packs_flake8": [],
            "fail_packs_XSOAR_linter": [],
            "fail_packs_bandit": [],
            "fail_packs_mypy": [],
            "fail_packs_vulture": [],
            "fail_packs_pylint": [],
            "fail_packs_pytest": [],
            "fail_packs_pwsh_analyze": [],
            "fail_packs_pwsh_test": [],
            "fail_packs_image": [],
            "warning_packs_flake8": [],
            "warning_packs_XSOAR_linter": [],
            "warning_packs_bandit": [],
            "warning_packs_mypy": [],
            "warning_packs_vulture": [],
            "warning_packs_pylint": [],
            "warning_packs_pytest": [],
            "warning_packs_pwsh_analyze": [],
            "warning_packs_pwsh_test": [],
            "warning_packs_image": [],
        }

        # Python or powershell or both
        pkgs_type = []

        # Detailed packages status
        pkgs_status = {}

        # Skiped lint and test codes
        skipped_code = build_skipped_exit_code(no_flake8=no_flake8, no_bandit=no_bandit, no_mypy=no_mypy,
                                               no_vulture=no_vulture, no_xsoar_linter=no_xsoar_linter,
                                               no_pylint=no_pylint, no_test=no_test, no_pwsh_analyze=no_pwsh_analyze,
                                               no_pwsh_test=no_pwsh_test, docker_engine=self._facts["docker_engine"])

        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as executor:
            return_exit_code: int = 0
            return_warning_code: int = 0
            results = []
            # Executing lint checks in different threads
            for package in sorted(self.packages, key=lambda package: package.path):
                results.append(executor.submit(self.run_linters,
                                               linters=self.get_linters(package)))
                # linter: Linter = Linter(pack_dir=pack,
                #                         content_repo="" if not self._facts["content_repo"] else
                #                         Path(self._facts["content_repo"].working_dir),
                #                         req_2=self._facts["requirements_2"],
                #                         req_3=self._facts["requirements_3"],
                #                         docker_engine=self._facts["docker_engine"],
                #                         docker_timeout=docker_timeout)
                # results.append(executor.submit(linter.run_dev_packages,
                #                                no_flake8=no_flake8,
                #                                no_bandit=no_bandit,
                #                                no_mypy=no_mypy,
                #                                no_vulture=no_vulture,
                #                                no_xsoar_linter=no_xsoar_linter,
                #                                no_pylint=no_pylint,
                #                                no_test=no_test,
                #                                no_pwsh_analyze=no_pwsh_analyze,
                #                                no_pwsh_test=no_pwsh_test,
                #                                modules=self._facts["test_modules"],
                #                                keep_container=keep_container,
                #                                test_xml=test_xml,
                #                                no_coverage=no_coverage))
            try:
                for future in concurrent.futures.as_completed(results):
                    pkg_status = future.result()
                    pkgs_status[pkg_status["pkg"]] = pkg_status
                    if pkg_status["exit_code"]:
                        for check, code in EXIT_CODES.items():
                            if pkg_status["exit_code"] & code:
                                lint_status[f"fail_packs_{check}"].append(pkg_status["pkg"])
                        if not return_exit_code & pkg_status["exit_code"]:
                            return_exit_code += pkg_status["exit_code"]
                    if pkg_status["warning_code"]:
                        for check, code in EXIT_CODES.items():
                            if pkg_status["warning_code"] & code:
                                lint_status[f"warning_packs_{check}"].append(pkg_status["pkg"])
                        if not return_warning_code & pkg_status["warning_code"]:
                            return_warning_code += pkg_status["warning_code"]
                    if pkg_status["pack_type"] not in pkgs_type:
                        pkgs_type.append(pkg_status["pack_type"])
            except KeyboardInterrupt:
                print_warning("Stop demisto-sdk lint - Due to 'Ctrl C' signal")
                try:
                    executor.shutdown(wait=False)
                except Exception:
                    pass
                return 1
            except Exception as e:
                print_warning(f"Stop demisto-sdk lint - Due to Exception {e}")
                try:
                    executor.shutdown(wait=False)
                except Exception:
                    pass
                return 1

        self._report_results(lint_status=lint_status,
                             pkgs_status=pkgs_status,
                             return_exit_code=return_exit_code,
                             return_warning_code=return_warning_code,
                             skipped_code=int(skipped_code),
                             pkgs_type=pkgs_type,
                             no_coverage=no_coverage,
                             coverage_report=coverage_report)
        self._create_failed_packs_report(lint_status=lint_status, path=failure_report)

        # check if there were any errors during lint run , if so set to FAIL as some error codes are bigger
        # then 512 and will not cause failure on the exit code.
        if return_exit_code:
            return_exit_code = FAIL
        return return_exit_code
