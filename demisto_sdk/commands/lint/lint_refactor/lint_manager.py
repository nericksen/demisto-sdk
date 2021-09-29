import concurrent.futures
import os
import traceback
from pathlib import Path
from typing import List, Set
from typing import Union

import click
from git import Repo
from wcmatch.pathlib import Path

from demisto_sdk.commands.common.constants import DemistoException
from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.common.logger import Colors
from demisto_sdk.commands.common.tools import print_v, print_warning
from demisto_sdk.commands.lint.lint_refactor.lint_constants import LintFlags
from demisto_sdk.commands.lint.lint_refactor.lint_global_facts import LintGlobalFacts, build_lint_global_facts
from demisto_sdk.commands.lint.lint_refactor.lint_package_facts import LintPackageFacts, build_package_facts
from demisto_sdk.commands.lint.lint_refactor.linters.abstract_linters.base_linter import BaseLinter
from demisto_sdk.commands.lint.lint_refactor.linters.bandit import BanditLinter
from demisto_sdk.commands.lint.lint_refactor.linters.flake8_linter import Flake8Linter
from demisto_sdk.commands.lint.lint_refactor.linters.mypy_linter import MyPyLinter
from demisto_sdk.commands.lint.lint_refactor.linters.pwsh_analyze_linter import PowershellAnalyzeLinter
from demisto_sdk.commands.lint.lint_refactor.linters.pwsh_test_linter import PowershellTestLinter
from demisto_sdk.commands.lint.lint_refactor.linters.pylint_linter import PylintLinter
from demisto_sdk.commands.lint.lint_refactor.linters.pytest_linter import PytestLinter
from demisto_sdk.commands.lint.lint_refactor.linters.vulture_linter import VultureLinter
from demisto_sdk.commands.lint.lint_refactor.linters.xsoar_linter import XSOARLinter
from demisto_sdk.commands.lint.lint_refactor.linters.abstract_linters.docker_base_linter import DockerBaseLinter


class LintManager:
    ALL_LINTERS_CLASSES: List = [BanditLinter, Flake8Linter, MyPyLinter, PowershellAnalyzeLinter,
                                 PowershellTestLinter, PylintLinter, PytestLinter, VultureLinter,
                                 XSOARLinter]
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
                 docker_timeout: int, keep_container: bool, no_flake8: bool, no_bandit: bool, no_mypy: bool,
                 no_pylint: bool, no_vulture: bool, no_xsoar_linter: bool, no_pwsh_analyze: bool, no_pwsh_test: bool,
                 no_pytest: bool, test_xml: str, no_coverage: bool, json_file_path: str = ''):

        # Verbosity level
        self._verbose = False if quiet else verbose
        self._prev_ver = prev_ver
        self._all_packs = all_packs
        # Set 'git' to true if no packs have been specified, 'lint' should operate as 'lint -g'
        git_only = git_only or (not all_packs and not input_dirs)
        # Gather facts for manager
        self.lint_global_facts: LintGlobalFacts = build_lint_global_facts(docker_timeout, keep_container, test_xml,
                                                                          self._verbose)
        self.lint_flags: LintFlags = LintFlags(
            disable_flake8=no_flake8,
            disable_bandit=no_bandit,
            disable_mypy=no_mypy,
            disable_pylint=no_pylint,
            disable_vulture=no_vulture,
            disable_xsoar_linter=no_xsoar_linter,
            disable_pwsh_analyze=no_pwsh_analyze,
            disable_pwsh_test=no_pwsh_test,
            disable_pytest=no_pytest,
            no_coverage=no_coverage
        )
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
            input_dirs: List[str] = input_dirs.split(',')
            packages: List[Union[Script, Integration]] = [package for input_dir in input_dirs for packages in
                                                          self._get_all_packages(input_dir) for package in packages]
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

    def get_linters(self, package: Union[Script, Integration], package_facts: LintPackageFacts) -> List[BaseLinter]:
        """
        Returns a list of all the linters that should run for the given package.
        Args:
            package (Union[Script, Integration]): Package to run linters on.
            package_facts (LintPackageFacts): Facts regarding given package.

        Returns:
            (List[BaseLinter]): List of linters to run on given package.
        """
        linters: List[BaseLinter] = []
        for linter_class in self.ALL_LINTERS_CLASSES:
            linter: BaseLinter = linter_class(self.lint_flags, self.lint_global_facts, package, package_facts)
            if linter.should_run():
                linters.append(linter)
        return linters

    @staticmethod
    def run_linters(linters: List[BaseLinter]):
        """
        Runs all given linters. Adds the result to the class list using `add_non_successful_package` function.
        Args:
            linters (List[BaseLinters]): Linters to run and analyze results.

        Returns:
            (None): Runs linters and saves result in the class lists `FAILED_PACKAGES` and `WARNING_PACKAGES`.
        """
        for linter in linters:
            linter_result, outputs = linter.run()
            linter.add_non_successful_package(linter_result, outputs)

    def analyze_results(self):
        for linter_class in self.ALL_LINTERS_CLASSES:
            linter_class.report_unsuccessful_lint_check(linter_class.LINTER_NAME)

    def run_dev_packages(self, parallel: int) -> int:
        """ Runs the Lint command on all given packages.

        Args:
            parallel(int): Whether to run command on multiple threads

        Returns:
            int: exit code by fail exit codes by var EXIT_CODES
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as executor:
            results = []
            # Executing lint checks in different threads
            try:
                for package in sorted(self.packages, key=lambda package_: package_.path):
                    package_facts: LintPackageFacts = build_package_facts(self.lint_global_facts, package)
                    results.append(executor.submit(self.run_linters, linters=self.get_linters(package, package_facts)))

            except KeyboardInterrupt:
                print_warning('Stopping demisto-sdk lint - Due to Ctrl C signal')
                try:
                    executor.shutdown(wait=False)
                except Exception:
                    pass
                return 1
            except Exception as e:
                print_warning(f'Stopping demisto-sdk lint - Due to Exception: {e}. '
                              f'Traceback:\n{traceback.format_exc()}')
        self.analyze_results()
        return 0
