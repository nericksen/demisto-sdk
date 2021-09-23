import json
import os
from typing import Union, Dict, Tuple, Optional

import click
from wcmatch.pathlib import Path

from demisto_sdk.commands.common.constants import TYPE_PYTHON
from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.lint.lint_refactor.coverage_utils import coverage_report_editor
from demisto_sdk.commands.lint.lint_refactor.lint_constants import LinterResult
from demisto_sdk.commands.lint.lint_refactor.lint_docker_utils import get_file_from_container
from demisto_sdk.commands.lint.lint_refactor.lint_flags import LintFlags
from demisto_sdk.commands.lint.lint_refactor.lint_global_facts import LintGlobalFacts
from demisto_sdk.commands.lint.lint_refactor.lint_package_facts import LintPackageFacts
from demisto_sdk.commands.lint.lint_refactor.linters.abstract_linters.docker_base_linter import DockerBaseLinter


class PylintLinter(DockerBaseLinter):
    # Dict of mapping docker exit code to a tuple (LinterResult, log prompt suffix, log prompt color)
    CONTAINER_EXIT_CODE_FOR_COVERAGE_AND_TEST_FILE = [0, 1, 2, 5]
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

    def __init__(self, lint_flags: LintFlags, lint_global_facts: LintGlobalFacts, package: Union[Script, Integration],
                 lint_package_facts: LintPackageFacts):
        super().__init__(lint_flags.disable_pytest, lint_global_facts, package, self.LINTER_NAME, lint_package_facts)
        self.report_coverage = not lint_flags.no_coverage

    def should_run(self) -> bool:
        return all([
            self.is_expected_package(TYPE_PYTHON),
            self.has_unit_tests(),
            super().should_run()
        ])

    def process_docker_results(self, container_obj, container_exit_code, log_prompt: str, test_xml: str = 'TODO'):
        if container_exit_code in self.CONTAINER_EXIT_CODE_FOR_COVERAGE_AND_TEST_FILE:
            self.handle_test_xml_file(container_obj)
            self.handle_coverage(container_obj)
        linter_result, log_prompt_suffix, log_color = self.DOCKER_EXIT_CODE_TO_LINTER_STATUS.get(
            container_exit_code, (LinterResult.SUCCESS, ' - Successfully finished', 'green'))
        click.secho(f'{log_prompt}{log_prompt_suffix}', fg=log_color)
        # TODO - see how to handle commented logic
        #                 test_json = json.loads(get_file_from_container(container_obj=container_obj,
        #                                                                container_path="/devwork/report_pytest.json",
        #                                                                encoding="utf-8"))
        #         for test in test_json.get('report', {}).get("tests"):
        #             if test.get("call", {}).get("longrepr"):
        #                 test["call"]["longrepr"] = test["call"]["longrepr"].split('\n')
        return linter_result

    def handle_test_xml_file(self, container_obj):
        xml_output_path: Optional[str] = self.lint_global_facts.pytest_xml_output
        if xml_output_path:
            test_data_xml = get_file_from_container(container_obj=container_obj,
                                                    container_path="/devwork/report_pytest.xml")
            xml_output_path = Path(xml_output_path) / f'{self.package.path}_pytest.xml'
            with open(file=xml_output_path, mode='bw') as f:
                f.write(test_data_xml)  # type: ignore

    def handle_coverage(self, container_obj):
        if self.report_coverage:
            cov_file_path = os.path.join(self.package.path, '.coverage')
            cov_data = get_file_from_container(container_obj=container_obj, container_path="/devwork/.coverage")
            cov_data = cov_data if isinstance(cov_data, bytes) else cov_data.encode()
            with open(cov_file_path, 'wb') as coverage_file:
                coverage_file.write(cov_data)
            coverage_report_editor(cov_file_path, os.path.join(self.package.path, f'{self.package.path.stem}.py'))

    def build_linter_command(self) -> str:
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
            command += f' --cov-report= --cov={self.package.path}'

        return command
