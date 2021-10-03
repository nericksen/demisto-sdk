from typing import Tuple, Union, Dict, Optional

from demisto_sdk.commands.common.constants import TYPE_PWSH
from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.lint.lint_constants import LintFlags
from demisto_sdk.commands.lint.lint_constants import LinterResult
from demisto_sdk.commands.lint.lint_global_facts import LintGlobalFacts
from demisto_sdk.commands.lint.lint_package_facts import LintPackageFacts
from demisto_sdk.commands.lint.linters.abstract_linters.docker_base_linter import DockerBaseLinter


class PowershellTestLinter(DockerBaseLinter):
    # Dict of mapping docker exit code to a tuple (LinterResult, log prompt suffix, log prompt color)
    DOCKER_EXIT_CODE_TO_LINTER_STATUS: Dict[int, Tuple[LinterResult, str, str]] = {
        # 1-fatal message issued
        1: (LinterResult.FAIL, ' - Finished errors found', 'red'),
        # 2-Error message issued
        2: (LinterResult.FAIL, ' - Finished errors found', 'red'),
    }
    LINTER_NAME = 'Powershell Test'

    def __init__(self, lint_flags: LintFlags, lint_global_facts: LintGlobalFacts):
        super().__init__(lint_flags.disable_pwsh_analyze, lint_global_facts, self.LINTER_NAME,
                         self.DOCKER_EXIT_CODE_TO_LINTER_STATUS)

    def should_run(self, package: Union[Script, Integration]) -> bool:
        return all([
            self.is_expected_package(package, TYPE_PWSH),
            super().should_run(package)
        ])

    def build_linter_command(self, package: Union[Script, Integration], lint_package_facts: LintPackageFacts,
                             docker_image: Optional[str] = None) -> str:
        """
        Build command for powershell test.
        Returns:
           (str): powershell test command.
        """
        # Return exit code when finished
        command = 'Invoke-Pester -Configuration \'@{Run=@{Exit=$true}; Output=@{Verbosity="Detailed"}}\''
        return f"pwsh -Command {command}"
