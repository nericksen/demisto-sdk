import os
from typing import Union, Optional

from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.lint.json_output_formatters import VultureFormatter
from demisto_sdk.commands.lint.lint_constants import LintFlags
from demisto_sdk.commands.lint.lint_global_facts import LintGlobalFacts
from demisto_sdk.commands.lint.lint_package_facts import LintPackageFacts
from demisto_sdk.commands.lint.linters.abstract_linters.python_base_linter import PythonBaseLinter


class VultureLinter(PythonBaseLinter):
    LINTER_NAME = 'Vulture'

    def __init__(self, lint_flags: LintFlags, lint_global_facts: LintGlobalFacts):
        super().__init__(lint_flags.disable_flake8, lint_global_facts, self.LINTER_NAME,
                         json_output_formatter=VultureFormatter())

    def should_run(self, package: Union[Script, Integration]) -> bool:
        return all([
            self.has_lint_files(),
            super().should_run(package)
        ])

    def build_linter_command(self, package: Union[Script, Integration], lint_package_facts: LintPackageFacts,
                             docker_image: Optional[str] = None) -> str:
        """
        Build command to execute with pylint module https://github.com/jendrikseipp/vulture.
        Returns:
           (str): vulture command.
        """
        python_version: float = self.get_python_version(package.script_type, lint_package_facts.images)
        command = f'{self.get_python_exec(python_version)} -m vulture'
        # Excluded files
        command += f" --min-confidence {os.environ.get('VULTURE_MIN_CONFIDENCE_LEVEL', '100')}"
        # File to be excluded when performing lints check
        command += f" --exclude={','.join(self.EXCLUDED_FILES)}"
        # Whitelist vulture
        whitelist = package.path.parent / '.vulture_whitelist.py'
        if whitelist.exists():
            command += f' {whitelist}'
        command += ' ' + ' '.join(lint_package_facts.lint_files)
        return command
