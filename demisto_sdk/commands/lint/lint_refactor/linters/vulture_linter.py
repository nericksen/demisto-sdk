import os
from typing import Union

from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.lint.lint_refactor.lint_flags import LintFlags
from demisto_sdk.commands.lint.lint_refactor.lint_global_facts import LintGlobalFacts
from demisto_sdk.commands.lint.lint_refactor.lint_package_facts import LintPackageFacts
from demisto_sdk.commands.lint.lint_refactor.linters.abstract_linters.python_base_linter import PythonBaseLinter


class VultureLinter(PythonBaseLinter):
    LINTER_NAME = 'Vulture'

    def __init__(self, lint_flags: LintFlags, lint_global_facts: LintGlobalFacts, package: Union[Script, Integration],
                 lint_package_facts: LintPackageFacts):
        super().__init__(lint_flags.disable_flake8, lint_global_facts, package, self.LINTER_NAME, lint_package_facts)

    def should_run(self) -> bool:
        return all([
            self.has_lint_files(),
            super().should_run()
        ])

    def build_linter_command(self) -> str:
        """
        Build command to execute with pylint module https://github.com/jendrikseipp/vulture.
        Returns:
           (str): vulture command.
        """
        command = f'{self.get_python_exec()} -m vulture'
        # Excluded files
        command += f" --min-confidence {os.environ.get('VULTURE_MIN_CONFIDENCE_LEVEL', '100')}"
        # File to be excluded when performing lints check
        command += f" --exclude={','.join(self.EXCLUDED_FILES)}"
        # Whitelist vulture
        whitelist = self.package.path / '.vulture_whitelist.py'
        if whitelist.exists():
            command += f' {whitelist}'
        command += ' ' + ' '.join(self.lint_package_facts.lint_files)
        return command
