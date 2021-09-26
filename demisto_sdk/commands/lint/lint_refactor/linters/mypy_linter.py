from typing import Union

from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.lint.lint_refactor.lint_flags import LintFlags
from demisto_sdk.commands.lint.lint_refactor.lint_global_facts import LintGlobalFacts
from demisto_sdk.commands.lint.lint_refactor.lint_package_facts import LintPackageFacts
from demisto_sdk.commands.lint.lint_refactor.linters.abstract_linters.python_base_linter import PythonBaseLinter


class MyPyLinter(PythonBaseLinter):
    LINTER_NAME = 'MyPy'
    HAS_ERRORS = False
    HAS_WARNINGS = False

    def __init__(self, lint_flags: LintFlags, lint_global_facts: LintGlobalFacts, package: Union[Script, Integration],
                 lint_package_facts: LintPackageFacts):
        super().__init__(lint_flags.disable_mypy, lint_global_facts, package, self.LINTER_NAME, lint_package_facts)

    def should_run(self) -> bool:
        return all([
            self.has_lint_files(),
            super().should_run()
        ])

    def build_linter_command(self) -> str:
        """
        Build command to execute with mypy module https://mypy.readthedocs.io/en/stable/command_line.html.
        Returns:
            (str): mypy command.
        """
        command = 'python3 -m mypy'
        # Define python versions
        command += f' --python-version {self.get_python_version()}'
        # This flag enable type checks the body of every function, regardless of whether it has type annotations.
        command += ' --check-untyped-defs'
        # This flag makes mypy ignore all missing imports.
        command += ' --ignore-missing-imports'
        # This flag adjusts how mypy follows imported modules that were not explicitly passed in via the command line
        command += ' --follow-imports=silent'
        # This flag will add column offsets to error messages.
        command += ' --show-column-numbers'
        # This flag will precede all errors with “note” messages explaining the context of the error.
        command += ' --show-error-codes'
        # Use visually nicer output in error messages
        command += ' --pretty'
        # This flag enables redefinition of a variable with an arbitrary type in some contexts.
        command += ' --allow-redefinition'
        # Get the full path to the file.
        command += ' --show-absolute-path'
        # Disable cache creation
        command += ' --cache-dir=/dev/null'
        # Generating path patterns - file1 file2 file3,..
        command += ' ' + ' '.join(self.lint_package_facts.lint_files)

        return command
