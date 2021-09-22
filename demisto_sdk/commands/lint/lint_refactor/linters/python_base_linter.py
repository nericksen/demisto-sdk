from abc import abstractmethod
from typing import Union

from demisto_sdk.commands.common.constants import (TYPE_PYTHON)
from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.lint.lint_refactor.lint_global_facts import LintGlobalFacts
from demisto_sdk.commands.lint.lint_refactor.lint_package_facts import LintPackageFacts
from demisto_sdk.commands.lint.lint_refactor.linters.base_linter import BaseLinter


class PythonBaseLinter(BaseLinter):
    DEFAULT_PYTHON3 = 3.7
    DEFAULT_PYTHON2 = 2.7

    def __init__(self, disable_flag: bool, lint_global_facts: LintGlobalFacts, package: Union[Script, Integration],
                 lint_name: str, lint_package_facts: LintPackageFacts):
        super().__init__(disable_flag, lint_global_facts, package, lint_name, lint_package_facts)

    @abstractmethod
    def build_linter_command(self) -> str:
        pass

    def should_run(self) -> bool:
        return all([
            self.is_expected_package(TYPE_PYTHON),
            super().should_run()
        ])

    def get_python_exec(self, is_py2: bool = False) -> str:
        """
        Get python executable
        Args:
            is_py2(bool): for python 2 version, Set True if the returned result should have python2 or False for python.

        Returns:
            str: python executable
        """
        python_version = self.get_python_version()
        py_num_str: str = '3'
        if python_version < 3:
            # Use default of python if is_py2 flag was not given.
            py_num_str = '2' if is_py2 else ''
        return f'python{py_num_str}'

    def get_python_version(self) -> float:
        if self.lint_global_facts.has_docker_engine:
            python_version = next((self.get_python_version_from_image(image) for image in
                                   self.lint_package_facts.images), self.DEFAULT_PYTHON3)
        else:
            # TODO: why default is python3 if subtype not found?
            python_version = self.DEFAULT_PYTHON3 if (self.package.script.get('subtype', 'python3') == 'python3') \
                else self.DEFAULT_PYTHON2
        return python_version
