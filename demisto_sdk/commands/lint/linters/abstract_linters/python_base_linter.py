from abc import abstractmethod
from typing import Union, Optional, List

from demisto_sdk.commands.common.constants import TYPE_PYTHON
from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.lint.json_output_formatters import Formatter
from demisto_sdk.commands.lint.lint_docker_utils import get_python_version_from_image
from demisto_sdk.commands.lint.lint_global_facts import LintGlobalFacts
from demisto_sdk.commands.lint.lint_package_facts import LintPackageFacts
from demisto_sdk.commands.lint.linters.abstract_linters.base_linter import BaseLinter


class PythonBaseLinter(BaseLinter):
    DEFAULT_PYTHON3 = 3.7
    DEFAULT_PYTHON2 = 2.7

    def __init__(self, disable_flag: bool, lint_global_facts: LintGlobalFacts, lint_name: str,
                 cwd_for_linter: Optional[str] = None, json_output_formatter: Optional[Formatter] = None):
        super().__init__(disable_flag, lint_global_facts, lint_name, cwd_for_linter=cwd_for_linter,
                         json_output_formatter=json_output_formatter)

    @abstractmethod
    def build_linter_command(self, package: Union[Script, Integration], lint_package_facts: LintPackageFacts) -> str:
        pass

    def should_run(self, package: Union[Script, Integration]) -> bool:
        return all([
            self.is_expected_package(package, TYPE_PYTHON),
            self.linter_is_not_disabled()
        ])

    @staticmethod
    def get_python_exec(python_version: float, is_py2: bool = False) -> str:
        """
        Get python executable
        Args:
            python_version (str): Python version to get its exec command for command OS.
            is_py2(bool): for python 2 version, Set True if the returned result should have python2 or False for python.

        Returns:
            str: python executable
        """
        py_num_str: str = '3'
        if python_version < 3:
            # Use default of python if is_py2 flag was not given.
            py_num_str = '2' if is_py2 else ''
        return f'python{py_num_str}'
