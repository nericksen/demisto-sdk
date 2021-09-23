from typing import Tuple, Union, Dict

from demisto_sdk.commands.common.constants import TYPE_PYTHON
from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.lint.lint_refactor.lint_constants import LinterResult
from demisto_sdk.commands.lint.lint_refactor.lint_flags import LintFlags
from demisto_sdk.commands.lint.lint_refactor.lint_global_facts import LintGlobalFacts
from demisto_sdk.commands.lint.lint_refactor.lint_package_facts import LintPackageFacts
from demisto_sdk.commands.lint.lint_refactor.linters.abstract_linters.docker_base_linter import DockerBaseLinter


class PylintLinter(DockerBaseLinter):
    # Dict of mapping docker exit code to a tuple (LinterResult, log prompt suffix, log prompt color)
    DOCKER_EXIT_CODE_TO_LINTER_STATUS: Dict[int, Tuple[LinterResult, str, str]] = {
        # 1-fatal message issued
        1: (LinterResult.FAIL, ' - Finished errors found', 'red'),
        # 2-Error message issued
        2: (LinterResult.FAIL, ' - Finished errors found', 'red'),
        # 4-Warning message issued
        4: (LinterResult.SUCCESS, ' - Successfully finished - warnings found', 'yellow'),
        # 8-refactor message issued
        8: (LinterResult.SUCCESS, ' - Successfully finished - warnings found', 'yellow'),
        # 16-convention message issued
        16: (LinterResult.SUCCESS, ' - Successfully finished - warnings found', 'yellow'),
        # 32-usage error
        32: (LinterResult.RERUN, ' - Finished - Usage error', 'red')
    }
    LINTER_NAME = 'Pylint'

    def __init__(self, lint_flags: LintFlags, lint_global_facts: LintGlobalFacts, package: Union[Script, Integration],
                 lint_package_facts: LintPackageFacts):
        super().__init__(lint_flags.disable_pylint, lint_global_facts, package, self.LINTER_NAME, lint_package_facts,
                         self.DOCKER_EXIT_CODE_TO_LINTER_STATUS)

    def should_run(self) -> bool:
        return all([
            self.is_expected_package(TYPE_PYTHON),
            self.has_lint_files(),
            super().should_run()
        ])

    def build_linter_command(self) -> str:
        """"
        Build command to execute with pylint module https://docs.pylint.org/en/1.6.0/run.html#invoking-pylint.
        Args:
        Returns:
           (str): pylint command.
        """
        command = 'python -m pylint'
        # Excluded files
        command += f" --ignore={','.join(self.EXCLUDED_FILES)}"
        # Prints only errors
        command += ' -E'
        # disable xsoar linter messages
        disable = ['bad-option-value']
        # TODO: remove when pylint will update its version to support py3.9
        # if docker_version and docker_version >= 3.9:
        #     disable.append('unsubscriptable-object')
        command += f" --disable={','.join(disable)}"
        # Disable specific errors
        command += ' -d duplicate-string-formatting-argument'
        # Message format
        command += " --msg-template='{abspath}:{line}:{column}: {msg_id} {obj}: {msg}'"
        # List of members which are set dynamically and missed by pylint inference system, and so shouldn't trigger
        # E1101 when accessed.
        command += " --generated-members=requests.packages.urllib3,requests.codes.ok"
        # Generating path patterns - file1 file2 file3,..
        command += " " + " ".join(self.lint_package_facts.lint_files)
        return command
