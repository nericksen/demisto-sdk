import json
import os
import re
from textwrap import TextWrapper
from typing import Union, Tuple, Optional, Dict, List

import click
from wcmatch.pathlib import Path

from demisto_sdk.commands.common.constants import TYPE_PYTHON
from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.common.logger import Colors
from demisto_sdk.commands.common.tools import (print_v)
from demisto_sdk.commands.lint.coverage_utils import coverage_report_editor
from demisto_sdk.commands.lint.lint_constants import LintFlags
from demisto_sdk.commands.lint.lint_constants import LinterResult, UnsuccessfulPackageReport
from demisto_sdk.commands.lint.lint_docker_utils import get_file_from_container
from demisto_sdk.commands.lint.lint_global_facts import LintGlobalFacts
from demisto_sdk.commands.lint.lint_constants import create_text_wrapper
from demisto_sdk.commands.lint.lint_package_facts import LintPackageFacts
from demisto_sdk.commands.lint.linters.abstract_linters.docker_base_linter import DockerBaseLinter


class PytestLinter(DockerBaseLinter):
    # Dict of mapping docker exit code to a tuple (LinterResult, log prompt suffix, log prompt color)
    CONTAINER_EXIT_CODE_FOR_COVERAGE_AND_TEST_FILE = [0, 1, 2, 5]
    FAILED_UNIT_TESTS_ERROR_CODE = 1
    DOCKER_EXIT_CODE_TO_LINTER_STATUS: Dict[int, Tuple[LinterResult, str, str]] = {
        # All tests passed.
        0: (LinterResult.SUCCESS, ' - Successfully finished - All tests have passed', 'red'),
        # Tests were collected and ran - some tests have failed.
        1: (LinterResult.FAIL, ' - Finished errors found - Some tests have failed', 'red'),
        # Test execution was interrupted by the user.
        2: (LinterResult.FAIL, ' - Finished errors found - Execution was interrupted by the user', 'red'),
        # Internal error occurred while executing tests.
        3: (LinterResult.RERUN, ' - Usage error - Internal error occurred during test execution', 'red'),
        # Pytest command line usage error
        4: (LinterResult.RERUN, ' - Usage error - Pytest command line usage error', 'red'),
        # No tests were collected.
        5: (LinterResult.SUCCESS, ' - Successfully finished - No tests were collected', 'red'),
    }
    LINTER_NAME = 'Pytest'
    # Dict of {package name: {image name: tests}}
    FAILURE_UNIT_TESTS: Dict[str, Dict[str, List[Dict]]] = {}
    SUCCESSFUL_UNIT_TESTS: Dict[str, Dict[str, List[Dict]]] = {}

    def __init__(self, lint_flags: LintFlags, lint_global_facts: LintGlobalFacts):
        super().__init__(lint_flags.disable_pytest, lint_global_facts, self.LINTER_NAME,
                         self.DOCKER_EXIT_CODE_TO_LINTER_STATUS)
        self.report_coverage = not lint_flags.no_coverage

    def should_run(self, package: Union[Script, Integration]) -> bool:
        return all([
            self.is_expected_package(package, TYPE_PYTHON),
            self.has_unit_tests(package),
            super().should_run(package)
        ])

    def process_docker_results(self, package: Union[Script, Integration], container_obj, container_exit_code,
                               test_image: str) -> LinterResult:
        """
        Overriding process results because pytest has special treatment for tests and coverage files.
        Args:
            package
            container_obj:
            container_exit_code:
            test_image:

        Returns:
            TODO
        """
        linter_result: LinterResult = super().process_docker_results(package.name, container_obj, container_exit_code,
                                                                     test_image)
        if container_exit_code in self.CONTAINER_EXIT_CODE_FOR_COVERAGE_AND_TEST_FILE:
            self.handle_test_xml_file(package.path.parent, container_obj)
            self.handle_coverage(package.path.parent, container_obj)
        # Save test reports
        test_json = json.loads(get_file_from_container(container_obj=container_obj,
                                                       container_path="/devwork/report_pytest.json",
                                                       encoding="utf-8"))
        test_reports = test_json.get('report', {}).get('tests', [])
        for test in test_reports:
            if test.get('call', {}).get('longrepr'):
                test['call']['longrepr'] = test['call']['longrepr'].split('\n')
        if container_exit_code != self.FAILED_UNIT_TESTS_ERROR_CODE:
            self.__class__.SUCCESSFUL_UNIT_TESTS[package.name][test_image] = test_reports
        else:
            self.__class__.FAILURE_UNIT_TESTS[package.name][test_image] = test_reports
        return linter_result

    def handle_test_xml_file(self, package_path: Path, container_obj):
        xml_output_path: Optional[str] = self.lint_global_facts.pytest_xml_output
        if xml_output_path:
            test_data_xml = get_file_from_container(container_obj=container_obj,
                                                    container_path="/devwork/report_pytest.xml")
            xml_output_path = Path(xml_output_path) / f'{package_path}_pytest.xml'
            with open(file=xml_output_path, mode='bw') as f:
                f.write(test_data_xml)  # type: ignore

    def handle_coverage(self, package_path: Path, container_obj):
        if self.report_coverage:
            cov_file_path = os.path.join(package_path, '.coverage')
            cov_data = get_file_from_container(container_obj=container_obj, container_path="/devwork/.coverage")
            cov_data = cov_data if isinstance(cov_data, bytes) else cov_data.encode()
            with open(cov_file_path, 'wb') as coverage_file:
                coverage_file.write(cov_data)
            coverage_report_editor(cov_file_path, os.path.join(package_path, f'{package_path.stem}.py'))

    def add_non_successful_package(self, package_name: str, linter_result: LinterResult, outputs: str):
        class_ = self.__class__
        if linter_result in [LinterResult.WARNING, LinterResult.FAIL]:
            errors, warnings, other = self.split_warnings_errors(outputs)
            if warnings:
                class_.WARNING_PACKAGES.append(UnsuccessfulPackageReport(package_name, '\n'.join(warnings)))
            error_msg = '\n'.join(errors) + '\n'.join(other)
            if error_msg:
                class_.FAILED_PACKAGES.append(UnsuccessfulPackageReport(package_name, error_msg))
                # TODO : in old linter, it does if errors else other. Why not take care of both anyway? check

    def build_linter_command(self, package: Union[Script, Integration], lint_package_facts: LintPackageFacts) -> str:
        """
        Build command to execute with pytest module https://docs.pytest.org/en/latest/usage.html.
        Returns:
            (str): pytest command.
        """
        command = "python -m pytest -ra"
        # Generating junit-xml report - used in circle ci
        if self.lint_global_facts.pytest_xml_output:
            command += " --junitxml=/devwork/report_pytest.xml"
        # Generating json report
        if json:
            command += " --json=/devwork/report_pytest.json"

        if self.report_coverage:
            command += f' --cov-report= --cov={package.path.parent}'

        return command

    def _report_successful_packages(self):
        if not self.SUCCESSFUL_UNIT_TESTS:
            return
        print_v(f"\n{Colors.Fg.green}Passed Unit-tests:{Colors.reset}", log_verbose=self.verbose)
        wrapper_pack: TextWrapper = create_text_wrapper(2, 'Package:')
        wrapper_docker_image: TextWrapper = create_text_wrapper(6, 'Docker:')
        wrapper_test: TextWrapper = create_text_wrapper(9, '')
        for package_name, image_to_tests_dict in self.SUCCESSFUL_UNIT_TESTS.items():
            print_v(wrapper_pack.fill(f"{Colors.Fg.green}{package_name}{Colors.reset}"), log_verbose=self.verbose)
            for image, tests in image_to_tests_dict.items():
                # TODO if not image errors here
                if tests:
                    print_v(wrapper_docker_image.fill(image), log_verbose=self.verbose)
                    for test_case in tests:
                        outcome = test_case.get('call', {}).get('outcome', '')
                        name = re.sub(pattern=r"\[.*\]", repl="", string=test_case.get('name', ''))
                        if outcome != 'passed':
                            name = f'{name} ({outcome.upper()})'
                        print_v(wrapper_test.fill(name), log_verbose=self.verbose)

    def _report_unsuccessful_packages(self):
        if not self.FAILURE_UNIT_TESTS:
            return
        wrapper_pack: TextWrapper = create_text_wrapper(2, 'Package:')
        wrapper_first_error: TextWrapper = create_text_wrapper(9, 'Error:')
        wrapper_sec_error: TextWrapper = create_text_wrapper(9, '         ')
        wrapper_docker_image: TextWrapper = create_text_wrapper(6, 'Docker:')
        wrapper_test: TextWrapper = create_text_wrapper(9, '')
        for package_name, image_to_tests_dict in self.FAILURE_UNIT_TESTS.items():
            print_v(wrapper_pack.fill(f'{Colors.Fg.green}{package_name}{Colors.reset}'), log_verbose=self.verbose)
            for image, tests in image_to_tests_dict.items():
                # TODO add else logic to tests here
                print_v(wrapper_docker_image.fill(image), log_verbose=self.verbose)
                failed_tests = [test for test in tests if test.get('call', {}).get('outcome') == 'failed']
                if failed_tests:
                    for test_case in failed_tests:
                        name = re.sub(pattern=r"\[.*\]", repl="", string=test_case.get('name', ''))
                        click.secho(wrapper_test.fill(name))
                        for i, long_representation in enumerate(test_case.get('call', {}).get('longrepr', [])):
                            if i == 0:
                                click.secho(wrapper_first_error.fill(f'{long_representation}\n'))
                            else:
                                click.secho(wrapper_sec_error.fill(f'{long_representation}\n'))
                else:
                    # TODO
                    pass

    def report_unit_tests(self):
        if self.verbose and self.FAILURE_UNIT_TESTS:
            click.secho(f'\n###########\nUnit Tests\n###########', fg='yellow')
        self._report_successful_packages()
        self._report_unsuccessful_packages()
