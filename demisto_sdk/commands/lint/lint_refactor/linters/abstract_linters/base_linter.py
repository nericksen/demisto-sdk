from abc import abstractmethod
from typing import Union, Dict, Optional

import click

from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.common.tools import print_v, run_command_os
from demisto_sdk.commands.lint.lint_refactor.lint_constants import LinterResult
from demisto_sdk.commands.lint.lint_refactor.lint_global_facts import LintGlobalFacts
from demisto_sdk.commands.lint.lint_refactor.lint_package_facts import LintPackageFacts


class BaseLinter:
    # Some files are needed to be excluded from some of the linters.
    EXCLUDED_FILES = ['CommonServerPython.py', 'demistomock.py', 'CommonServerUserPython.py', 'conftest.py', 'venv']

    def __init__(self, disable_flag: bool, lint_global_facts: LintGlobalFacts, package: Union[Script, Integration],
                 linter_name: str, lint_package_facts: LintPackageFacts, env: Dict,
                 cwd_for_linter: Optional[str] = None):
        self.disable_flag = disable_flag
        self.lint_global_facts = lint_global_facts
        self.package = package
        self.repo_path = '' if not lint_global_facts.content_repo else lint_global_facts.content_repo.working_dir
        self.verbose = lint_global_facts.verbose
        self.linter_name = linter_name
        self.lint_package_facts = lint_package_facts
        self.env = env
        self.cwd_for_linter = cwd_for_linter if cwd_for_linter else str(self.package.path)

    def should_run(self) -> bool:
        return not self.disable_flag

    def has_lint_files(self) -> bool:
        return True if self.lint_global_facts.test_modules else False

    def has_unit_tests(self) -> bool:
        return True if self.package.unit_test_file else False

    def is_expected_package(self, package_type: str):
        return self.package.script_type == package_type

    def run(self):
        log_prompt: str = f'{self.package.name()} - {self.linter_name}'
        click.secho(f'{log_prompt} - Start', fg='bright_cyan')
        stdout, stderr, exit_code = run_command_os(command=self.build_linter_command(),
                                                   cwd=self.cwd_for_linter, env=self.env)
        print_v(f'{log_prompt} - Finished exit-code: {exit_code}', self.verbose)
        if stdout:
            print_v(f'{log_prompt} - Finished. STDOUT:\n{stdout}', self.verbose)
        if stderr:
            print_v(f'{log_prompt} - Finished. STDOUT:\n{stderr}', self.verbose)
        if stderr or exit_code:
            click.secho(f'{log_prompt}- Finished errors found', fg='red')
            if stderr:
                return LinterResult.FAIL, stderr
            else:
                return LinterResult.FAIL, stdout

        click.secho(f'{log_prompt} - Successfully finished', fg='green')

        return LinterResult.SUCCESS, ''

    @abstractmethod
    def build_linter_command(self) -> str:
        pass
