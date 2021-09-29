import os
from contextlib import contextmanager
from pathlib import Path
from typing import List
from typing import Union, Dict

import click

from demisto_sdk.commands.common.constants import SCRIPTS_DIR
from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.common.tools import get_pack_metadata
from demisto_sdk.commands.common.tools import print_v, run_command_os
from demisto_sdk.commands.lint.lint_refactor.lint_constants import LintFlags
from demisto_sdk.commands.lint.lint_refactor.lint_constants import LinterResult, XSOARLinterExitCode
from demisto_sdk.commands.lint.lint_refactor.lint_global_facts import LintGlobalFacts
from demisto_sdk.commands.lint.lint_refactor.lint_package_facts import LintPackageFacts
from demisto_sdk.commands.lint.lint_refactor.linters.abstract_linters.python_base_linter import PythonBaseLinter
from demisto_sdk.commands.lint.resources.pylint_plugins.base_checker import base_msg
from demisto_sdk.commands.lint.resources.pylint_plugins.certified_partner_level_checker import cert_partner_msg
from demisto_sdk.commands.lint.resources.pylint_plugins.community_level_checker import community_msg
from demisto_sdk.commands.lint.resources.pylint_plugins.partner_level_checker import partner_msg
from demisto_sdk.commands.lint.resources.pylint_plugins.xsoar_level_checker import xsoar_msg


class XSOARLinter(PythonBaseLinter):
    LINTER_NAME = 'XSOAR Linter'
    # linters by support level
    SUPPORT_LEVEL_TO_CHECK_DICT: Dict[str, str] = {
        'base': 'base_checker',
        'community': 'base_checker,community_level_checker',
        'partner': 'base_checker,community_level_checker,partner_level_checker',
        'certified partner': 'base_checker,community_level_checker,partner_level_checker,'
                             'certified_partner_level_checker',
        'xsoar': 'base_checker,community_level_checker,partner_level_checker,certified_partner_level_checker,'
                 'xsoar_level_checker'
    }

    def __init__(self, lint_flags: LintFlags, lint_global_facts: LintGlobalFacts, package: Union[Script, Integration],
                 lint_package_facts: LintPackageFacts):
        env = self.build_linter_env()
        super().__init__(lint_flags.disable_flake8, lint_global_facts, package, self.LINTER_NAME, lint_package_facts,
                         env=env)

    def should_run(self) -> bool:
        return all([
            self.has_lint_files(),
            super().should_run()
        ])

    def run(self) -> None:
        """
        Overriding the BaseLinter `run` method because XSOAR Linter has specific use case for running
        - Adding Pylint plugin.
        - Reporting the results.
        Returns:

        """
        linter_result = LinterResult.SUCCESS
        with _pylint_plugin(self.package.path):
            log_prompt: str = f'{self.package.name()} - XSOAR Linter'
            click.secho(f'{log_prompt} - Start', fg='bright_cyan')
            stdout, stderr, exit_code = run_command_os(command=self.build_linter_command(),
                                                       cwd=self.cwd_for_linter, env=self.env)
            if exit_code & XSOARLinterExitCode.WARNING.value:
                linter_result = LinterResult.WARNING
                click.secho(f'{log_prompt} - Finished: warnings found', fg='yellow')

            # If failure occurred, override status from warning to failure.
            if exit_code & XSOARLinterExitCode.PYLINT_FAILURE.value:
                linter_result = LinterResult.FAIL
                click.secho(f'{log_prompt} - Finished: errors found', fg='red')

            if exit_code & XSOARLinterExitCode.FAIL.value:
                linter_result = LinterResult.FAIL
                click.secho(f'{log_prompt} - Finished: errors found', fg='red')
                print_v(f'{log_prompt} - Actual XSOAR Linter error\n', self.verbose)
                stdout_verbose_suffix: str = f'\n{stdout}' if stdout else '\nNo STDOUT'
                if stdout:
                    print_v(f'{log_prompt} - Full stdout format: {stdout_verbose_suffix}', self.verbose)
                if os.environ.get('CI'):
                    stdout = "XSOAR Linter could not run, Please merge from master"
                else:
                    stdout = "XSOAR Linter could not run, please make sure you have" \
                             " the necessary Pylint version for both py2 and py3"
                click.secho(f'{log_prompt} - Finished: errors found', fg='red')

            print_v(f'{log_prompt} - Finished exit-code: {exit_code}', self.verbose)
            if stdout:
                print_v(f'{log_prompt} - Finished. STDOUT:\n{stdout}', self.verbose)
            if stderr:
                print_v(f'{log_prompt} - Finished. STDOUT:\n{stderr}', self.verbose)

            if linter_result == LinterResult.SUCCESS:
                click.secho(f'{log_prompt} - Successfully finished', fg='green')

            self.add_non_successful_package(linter_result, stdout)

    def build_linter_env(self) -> Dict:
        """
        Builds the environment for running the XSOAR Linter.
        As Xsoar checker is a pylint plugin and runs as part of pylint code, we can not pass args to it.
        As a result we can use the env vars as a gateway.
        Returns:
            (Dict): The environment, enriched with needed env vars for running XSOAR Linter.
        """
        my_env: Dict = os.environ.copy()

        python_version = self.get_python_version()
        if 'PYTHONPATH' in my_env:
            my_env['PYTHONPATH'] += ':' + str(self.package.path)
        else:
            my_env['PYTHONPATH'] = str(self.package.path)

        if self.package.script.get('longRunning'):
            my_env['LONGRUNNING'] = 'True'

        if python_version < 3:
            my_env['PY2'] = 'True'

        my_env['is_script'] = str(os.path.basename(os.path.dirname(self.package.path)) == SCRIPTS_DIR)

        commands_dict: Dict = self.package.script.get('commands', {})
        commands_names: List[str] = [command.get('name') for command in commands_dict if 'name' in command]
        my_env['commands'] = ','.join(commands_names) if commands_names else ''

        my_env['runas'] = self.package.script.get('runas', '')

        return my_env

    def build_linter_command(self) -> str:
        """
        Build command to execute with XSOAR Linter.
        Returns:
           (str): XSOAR Linter command using pylint load plugins.
        """
        support_level: str = get_pack_metadata(str(self.package.path)).get('support_level', 'base')

        # messages from all level linters
        check_to_xsoar_msg: Dict[str, Dict] = {'base_checker': base_msg, 'community_level_checker': community_msg,
                                               'partner_level_checker': partner_msg,
                                               'certified_partner_level_checker': cert_partner_msg,
                                               'xsoar_level_checker': xsoar_msg}

        checker_path = ""
        message_enable = ""
        if self.SUPPORT_LEVEL_TO_CHECK_DICT.get(support_level):
            checkers: str = self.SUPPORT_LEVEL_TO_CHECK_DICT.get(support_level)
            support: List[str] = checkers.split(',') if checkers else []
            for checker in support:
                checker_path += f'{checker},'
                checker_msgs_list = check_to_xsoar_msg.get(checker, {}).keys()
                for msg in checker_msgs_list:
                    message_enable += f'{msg},'

        command = f'{self.get_python_exec(is_py2=True)} -m pylint'
        # Excluded files
        command += f" --ignore={','.join(self.EXCLUDED_FILES)}"
        # Disable all errors
        command += ' -E --disable=all'
        # Message format
        command += " --msg-template='{abspath}:{line}:{column}: {msg_id} {obj}: {msg}'"
        # Enable only Demisto Plugins errors.
        command += f' --enable={message_enable}'
        # Load plugins
        if checker_path:
            command += f' --load-plugins {checker_path}'
        # Generating path patterns - file1 file2 file3,..
        command += ' ' + ' '.join(self.lint_package_facts.lint_files)
        return command


@contextmanager
def _pylint_plugin(package_path: Path):
    """
    Function which links the given path with the content of pylint plugins folder in resources.
    The main purpose is to link each pack with the pylint plugins.
    Args:
        package_path (Path): Pack path.
    """
    plugin_dirs = Path(__file__).parent / 'resources' / 'pylint_plugins'

    try:
        for file in plugin_dirs.iterdir():
            if file.is_file() and file.name != '__pycache__' and file.name.split('.')[1] != 'pyc':
                os.symlink(file, package_path / file.name)

        yield
    finally:
        for file in plugin_dirs.iterdir():
            if file.is_file() and file.name != '__pycache__' and file.name.split('.')[1] != 'pyc':
                if os.path.lexists(package_path / f'{file.name}'):
                    (package_path / f'{file.name}').unlink()
