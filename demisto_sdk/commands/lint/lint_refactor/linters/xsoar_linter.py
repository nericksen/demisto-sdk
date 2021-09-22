import os
from typing import Union, Dict, List

from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.lint.lint_refactor.lint_flags import LintFlags
from demisto_sdk.commands.lint.lint_refactor.lint_global_facts import LintGlobalFacts
from demisto_sdk.commands.lint.lint_refactor.lint_package_facts import LintPackageFacts
from demisto_sdk.commands.lint.lint_refactor.linters.python_base_linter import PythonBaseLinter
from demisto_sdk.commands.common.tools import get_pack_metadata


class VultureLinter(PythonBaseLinter):
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
        super().__init__(lint_flags.disable_flake8, lint_global_facts, package, self.LINTER_NAME, lint_package_facts)

    def should_run(self) -> bool:
        return all([
            self.has_lint_files(),
            super().should_run()
        ])

    def run(self):
        """ Runs Xsaor linter in pack dir

                Args:
                    lint_files(List[Path]): file to perform lint

                Returns:
                   int:  0 on successful else 1, errors
                   str: Xsoar linter errors
                """
        status = SUCCESS
        FAIL_PYLINT = 0b10
        with pylint_plugin(self._pack_abs_dir):
            log_prompt = f"{self._pack_name} - XSOAR Linter"
            logger.info(f"{log_prompt} - Start")
            myenv = os.environ.copy()
            if myenv.get('PYTHONPATH'):
                myenv['PYTHONPATH'] += ':' + str(self._pack_abs_dir)
            else:
                myenv['PYTHONPATH'] = str(self._pack_abs_dir)
            if self._facts['is_long_running']:
                myenv['LONGRUNNING'] = 'True'
            if py_num < 3:
                myenv['PY2'] = 'True'
            myenv['is_script'] = str(self._facts['is_script'])
            # as Xsoar checker is a pylint plugin and runs as part of pylint code, we can not pass args to it.
            # as a result we can use the env vars as a getway.
            myenv['commands'] = ','.join([str(elem) for elem in self._facts['commands']]) \
                if self._facts['commands'] else ''
            myenv['runas'] = self._facts['runas']
            stdout, stderr, exit_code = run_command_os(
                command=build_xsoar_linter_command(lint_files, py_num, self._facts.get('support_level', 'base')),
                cwd=self._pack_abs_dir, env=myenv)
        if exit_code & FAIL_PYLINT:
            logger.info(f"{log_prompt}- Finished errors found")
            status = FAIL
        if exit_code & WARNING:
            logger.info(f"{log_prompt} - Finished warnings found")
            if not status:
                status = WARNING
        # if pylint did not run and failure exit code has been returned from run commnad
        elif exit_code & FAIL:
            status = FAIL
            logger.debug(f"{log_prompt} - Actual XSOAR linter error -")
            logger.debug(f"{log_prompt} - Full format stdout: {RL if stdout else ''}{stdout}")
            # for contrib prs which are not merged from master and do not have pylint in dev-requirements-py2.
            if os.environ.get('CI'):
                stdout = "Xsoar linter could not run, Please merge from master"
            else:
                stdout = "Xsoar linter could not run, please make sure you have" \
                         " the necessary Pylint version for both py2 and py3"
            logger.info(f"{log_prompt}- Finished errors found")

        logger.debug(f"{log_prompt} - Finished exit-code: {exit_code}")
        logger.debug(f"{log_prompt} - Finished stdout: {RL if stdout else ''}{stdout}")
        logger.debug(f"{log_prompt} - Finished stderr: {RL if stderr else ''}{stderr}")

        if not exit_code:
            logger.info(f"{log_prompt} - Successfully finished")

        return status, stdout


    def get_linter_env():
        my_env = os.environ.copy()
        package_path = self._pack_abs_dir
        my_env['PYTHONPATH'] = f"{my_env.get('PYTHONPATH', '')}"
    def build_linter_command(self) -> str:
        """ Build command to execute with xsoar linter module
        Args:
            py_num(float): The python version in use
            files(List[Path]): files to execute lint
            support_level: Support level for the file

        Returns:
           str: xsoar linter command using pylint load plugins
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
