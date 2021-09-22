from typing import Union

from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.lint.lint_refactor.lint_flags import LintFlags
from demisto_sdk.commands.lint.lint_refactor.lint_global_facts import LintGlobalFacts
from demisto_sdk.commands.lint.lint_refactor.lint_package_facts import LintPackageFacts
from demisto_sdk.commands.lint.lint_refactor.linters.docker_base_linter import DockerBaseLinter


class PylintLinter(DockerBaseLinter):
    LINTER_NAME = 'Pylint'

    def __init__(self, lint_flags: LintFlags, lint_global_facts: LintGlobalFacts, package: Union[Script, Integration],
                 lint_package_facts: LintPackageFacts):
        super().__init__(lint_flags.disable_flake8, lint_global_facts, package, self.LINTER_NAME, lint_package_facts)

    def should_run(self) -> bool:
        return all([
            self.is_expected_package(''),
            self.has_lint_files(),
            super().should_run()
        ])

    def build_linter_command(self) -> str:
        """" Build command to execute with pylint module
                https://docs.pylint.org/en/1.6.0/run.html#invoking-pylint
            Args:
                files(List[Path]): files to execute lint
                docker_version: The version of the python docker image.
            Returns:
               str: pylint command
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
