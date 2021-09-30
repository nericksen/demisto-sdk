from abc import abstractmethod
from typing import Union, Optional, List, Tuple

import click

from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.common.logger import Colors
from demisto_sdk.commands.common.tools import print_v, run_command_os
from demisto_sdk.commands.lint.json_output_formatters import Formatter
from demisto_sdk.commands.lint.lint_constants import LinterResult, UnsuccessfulPackageReport, print_title
from demisto_sdk.commands.lint.lint_global_facts import LintGlobalFacts
from demisto_sdk.commands.lint.lint_package_facts import LintPackageFacts


class BaseLinter:
    # Some files are needed to be excluded from some of the linters.
    EXCLUDED_FILES = ['CommonServerPython.py', 'demistomock.py', 'CommonServerUserPython.py', 'conftest.py', 'venv']
    FAILED_PACKAGES: List[UnsuccessfulPackageReport] = []
    WARNING_PACKAGES: List[UnsuccessfulPackageReport] = []
    LENGTH_OF_LONGEST_LINTER_NAME: int = 0

    def __init__(self, disable_flag: bool, lint_global_facts: LintGlobalFacts, linter_name: str,
                 cwd_for_linter: Optional[str] = None, json_output_formatter: Optional[Formatter] = None):
        self.disable_flag = disable_flag
        self.lint_global_facts = lint_global_facts
        self.repo_path = '' if not lint_global_facts.content_repo else lint_global_facts.content_repo.working_dir
        self.verbose = lint_global_facts.verbose
        self.linter_name = linter_name
        BaseLinter.LENGTH_OF_LONGEST_LINTER_NAME = max(BaseLinter.LENGTH_OF_LONGEST_LINTER_NAME, len(linter_name))
        self.__class__.LINTER_NAME = linter_name
        self.cwd_for_linter = cwd_for_linter
        self.json_output_formatter = json_output_formatter

    @abstractmethod
    def should_run(self, package: Union[Script, Integration]):
        pass

    def linter_is_not_disabled(self) -> bool:
        return not self.disable_flag

    def has_lint_files(self) -> bool:
        return True if self.lint_global_facts.test_modules else False

    @staticmethod
    def has_unit_tests(package: Union[Script, Integration]) -> bool:
        return True if package.unittest_path else False

    @staticmethod
    def is_expected_package(package: Union[Script, Integration], package_type: str):
        return package.script_type == package_type

    def run(self, package: Union[Script, Integration], lint_package_facts: LintPackageFacts) -> None:
        linter_result, output = LinterResult.SUCCESS, ''
        cwd_for_linter: str = self.cwd_for_linter if self.cwd_for_linter else str(package.path.parent)
        log_prompt: str = f'{package.name} - {self.linter_name}'
        click.secho(f'{log_prompt} - Start', fg='bright_cyan')
        stdout, stderr, exit_code = run_command_os(command=self.build_linter_command(package, lint_package_facts),
                                                   cwd=cwd_for_linter)
        print_v(f'{log_prompt} - Finished exit-code: {exit_code}', self.verbose)
        if stdout:
            print_v(f'{log_prompt} - Finished. STDOUT:\n{stdout}', self.verbose)
        if stderr:
            print_v(f'{log_prompt} - Finished. STDOUT:\n{stderr}', self.verbose)
        if stderr or exit_code:
            click.secho(f'{log_prompt}- Finished errors found', fg='red')
            if stderr:
                linter_result, output = LinterResult.FAIL, stderr
            else:
                linter_result, output = LinterResult.FAIL, stdout

        click.secho(f'{log_prompt} - Successfully finished', fg='green')
        self.add_non_successful_package(package.name, linter_result, output)

    def add_non_successful_package(self, package_name: str, linter_result: LinterResult, outputs: str):
        if linter_result in [LinterResult.WARNING, LinterResult.FAIL]:
            errors, warnings, other = self.split_warnings_errors(outputs)
            if warnings:
                self.WARNING_PACKAGES.append(UnsuccessfulPackageReport(package_name, '\n'.join(warnings)))
            error_msg = '\n'.join(errors) + '\n'.join(other)
            if error_msg:
                self.FAILED_PACKAGES.append(UnsuccessfulPackageReport(package_name, error_msg))
                # TODO : in old linter, it does if errors else other. Why not take care of both anyway? check

    @abstractmethod
    def build_linter_command(self, package: Union[Script, Integration], lint_package_facts: LintPackageFacts) -> str:
        pass

    @staticmethod
    def split_warnings_errors(output: str) -> Tuple[List[str], List[str], List[str]]:
        """
        Function which splits the given string into warning messages and error using W or E in the beginning of string.
        For error messages that do not start with E, they will be returned as other.
        The output of a certain pack can both include:
        - Fail messages.
        - Fail messages and warnings messages.
        - Passed messaged.
        - Passed messages and warnings messages.
        - Warning messages.
        Args:
            output (str): String which contains messages from linters.
        return:
            (Tuple[List[str], List[str], List[str]): List of error messages,
                                                     list of warnings messages,
                                                     list of all undetected messages.
        """
        output_lst = output.split('\n')
        # Warnings and errors lists currently relevant for XSOAR Linter
        warnings_list = []
        error_list = []
        # Others list is relevant for mypy and flake8.
        other_msg_list = []
        for msg in output_lst:
            # 'W:' for python2 xsoar linter
            # 'W[0-9]' for python3 xsoar linter
            if (msg.startswith('W') and msg[1].isdigit()) or 'W:' in msg or 'W90' in msg:
                warnings_list.append(msg)
            elif (msg.startswith('E') and msg[1].isdigit()) or 'E:' in msg or 'E90' in msg:
                error_list.append(msg)
            else:
                other_msg_list.append(msg)

        return error_list, warnings_list, other_msg_list

    def report_pass_lint_check(self) -> str:
        spacing: int = BaseLinter.LENGTH_OF_LONGEST_LINTER_NAME - len(self.linter_name)
        if self.disable_flag:
            return f'{self.linter_name} {" " * spacing}- {Colors.Fg.cyan}[SKIPPED]{Colors.reset}'
        elif self.FAILED_PACKAGES:
            return f'{self.linter_name} {" " * spacing}- {Colors.Fg.red}[FAIL]{Colors.reset}'
        else:
            return f'{self.linter_name} {" " * spacing}- {Colors.Fg.green}[PASS]{Colors.reset}'

    def report_unsuccessful_lint_check(self):
        def _report_unsuccessful(unsuccessful_list: List[UnsuccessfulPackageReport], title_suffix: str, log_color: str):
            if not unsuccessful_list:
                return
            print_title(f'{self.linter_name} {title_suffix}', log_color=log_color)
            for unsuccessful_package_report in unsuccessful_list:
                click.secho(f'{unsuccessful_package_report.package_name}\n{unsuccessful_package_report.outputs}',
                            fg=log_color)

        _report_unsuccessful(self.FAILED_PACKAGES, 'Errors', 'red')
        _report_unsuccessful(self.WARNING_PACKAGES, 'Warnings', 'yellow')

    def create_json_output(self):
        if not self.json_output_formatter:
            return []
        fail_package_format = self.json_output_formatter.format('error', self.FAILED_PACKAGES)
        warning_package_format = self.json_output_formatter.format('warning', self.WARNING_PACKAGES)
        return fail_package_format + warning_package_format
