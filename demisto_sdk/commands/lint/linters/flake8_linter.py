from typing import Union, Optional

from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.lint.lint_constants import LintFlags
from demisto_sdk.commands.lint.lint_global_facts import LintGlobalFacts
from demisto_sdk.commands.lint.lint_package_facts import LintPackageFacts
from demisto_sdk.commands.lint.linters.abstract_linters.python_base_linter import PythonBaseLinter
from demisto_sdk.commands.lint.json_output_formatters import Flake8Formatter


class Flake8Linter(PythonBaseLinter):
    LINTER_NAME = 'Flake8'

    def __init__(self, lint_flags: LintFlags, lint_global_facts: LintGlobalFacts):
        cwd_for_linter: str = '' if not lint_global_facts.content_repo else lint_global_facts.content_repo.working_dir
        super().__init__(lint_flags.disable_flake8, lint_global_facts, self.LINTER_NAME, cwd_for_linter=cwd_for_linter,
                         json_output_formatter=Flake8Formatter())

    def should_run(self, package: Union[Script, Integration]) -> bool:
        return all([
            (self.has_lint_files() or self.has_unit_tests(package)),
            super().should_run(package)
        ])

    def build_linter_command(self, package: Union[Script, Integration], lint_package_facts: LintPackageFacts,
                             docker_image: Optional[str] = None) -> str:
        """
        Build command for executing flake8 lint check https://flake8.pycqa.org/en/latest/user/invocation.html.
        Returns:
            (str): flake8 command.
        """
        python_version: float = self.get_python_version(package.script_type, lint_package_facts.images)
        # Generating file patterns - path1,path2,path3,..
        command = f'''{self.get_python_exec(python_version)} -m flake8 {' '.join(lint_package_facts.lint_files)}'''

        return command
