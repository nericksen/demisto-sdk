from typing import Union

from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.lint.lint_refactor.lint_flags import LintFlags
from demisto_sdk.commands.lint.lint_refactor.lint_global_facts import LintGlobalFacts
from demisto_sdk.commands.lint.lint_refactor.lint_package_facts import LintPackageFacts
from demisto_sdk.commands.lint.lint_refactor.linters.python_base_linter import PythonBaseLinter


class Flake8Linter(PythonBaseLinter):
    LINTER_NAME = 'Flake8'

    def __init__(self, lint_flags: LintFlags, lint_global_facts: LintGlobalFacts, package: Union[Script, Integration],
                 lint_package_facts: LintPackageFacts):
        super().__init__(lint_flags.disable_flake8, lint_global_facts, package, self.LINTER_NAME, lint_package_facts)

    def should_run(self) -> bool:
        return all([
            (self.has_lint_files() or self.has_unit_tests()),
            super().should_run()
        ])

    def build_linter_command(self) -> str:
        """
        Build command for executing flake8 lint check https://flake8.pycqa.org/en/latest/user/invocation.html
        Returns:
            (str): flake8 command
        """
        files_list = [str(file) for file in self.lint_package_facts.lint_files]
        # TODO: add to package facts the python number
        # Generating file patterns - path1,path2,path3,..
        command = f'''{self.get_python_exec()} -m flake8 {' '.join(files_list)}'''

        return command
