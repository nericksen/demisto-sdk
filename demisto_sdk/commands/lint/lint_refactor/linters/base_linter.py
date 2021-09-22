import os
import shlex
from abc import abstractmethod
from functools import lru_cache
from typing import Union

import click
import docker
import docker.errors
from docker.models.containers import Container

from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.common.tools import print_v
from demisto_sdk.commands.common.tools import print_warning
from demisto_sdk.commands.common.tools import (run_command_os)
from demisto_sdk.commands.lint.lint_refactor.lint_global_facts import LintGlobalFacts
from demisto_sdk.commands.lint.lint_refactor.linters.lint_constants import LinterResult
from demisto_sdk.commands.lint.lint_refactor.lint_package_facts import LintPackageFacts


class BaseLinter:
    # Some files are needed to be excluded from some of the linters.
    EXCLUDED_FILES = ['CommonServerPython.py', 'demistomock.py', 'CommonServerUserPython.py', 'conftest.py', 'venv']

    def __init__(self, disable_flag: bool, lint_global_facts: LintGlobalFacts, package: Union[Script, Integration],
                 linter_name: str, lint_package_facts: LintPackageFacts, env=os.environ):
        self.disable_flag = disable_flag
        self.lint_global_facts = lint_global_facts
        self.package = package
        self.repo_path = '' if not lint_global_facts.content_repo else lint_global_facts.content_repo.working_dir
        self.verbose = lint_global_facts.verbose
        self.linter_name = linter_name
        self.lint_package_facts = lint_package_facts
        self.env = env

    def should_run(self) -> bool:
        return not self.disable_flag

    def has_lint_files(self) -> bool:
        return True if self.lint_global_facts.test_modules else False

    def has_unit_tests(self) -> bool:
        return True if self.package.unit_test_file else False

    def is_expected_package(self, package_type: str):
        return self.package.script_type == package_type

    def run(self):
        log_prompt: str = f'{self.package.name()} - {self.linter_name}'
        click.secho(log_prompt, fg='bright_cyan')
        stdout, stderr, exit_code = run_command_os(command=self.build_linter_command(),
                                                   cwd=self.repo_path, env=self.env)
        print_v(f'{log_prompt} - Finished exit-code: {exit_code}', self.verbose)
        if stdout:
            print_v(f'{log_prompt} - Finished. STDOUT:\n{stdout}')
        if stderr:
            print_v(f'{log_prompt} - Finished. STDOUT:\n{stderr}')
        if stderr or exit_code:
            click.secho(f'{log_prompt}- Finished errors found', fg='red')
            if stderr:
                return LinterResult.FAIL, stderr
            else:
                return LinterResult.FAIL, stdout

        click.secho(f'{log_prompt} - Successfully finished', fg='green')

        return LinterResult.SUCCESS, ''

    @abstractmethod
    def build_linter_command(self) -> str:
        pass

    @staticmethod
    @lru_cache(maxsize=100)
    def get_python_version_from_image(image: str, timeout: int = 60, log_prompt: str = '') -> float:
        """ Get python version from docker image

        Args:
            image(str): Docker image id or name
            timeout(int): Docker client request timeout
            log_prompt:  TODO

        Returns:
            float: Python version X.Y (3.7, 3.6, ..)
        """
        # skip powershell images
        if 'pwsh' in image or 'powershell' in image:
            return 3.8

        docker_user = os.getenv('DOCKERHUB_USER')
        docker_pass = os.getenv('DOCKERHUB_PASSWORD')
        docker_client = docker.from_env(timeout=timeout)
        docker_client.login(username=docker_user,
                            password=docker_pass,
                            registry="https://index.docker.io/v1")
        py_num = 3.8
        # Run three times
        for attempt in range(3):
            try:
                command = "python -c \"import sys; print('{}.{}'.format(sys.version_info[0], sys.version_info[1]))\""

                container_obj: Container = docker_client.containers.run(
                    image=image,
                    command=shlex.split(command),
                    detach=True
                )
                # Wait for container to finish
                container_obj.wait(condition="exited")
                # Get python version
                py_num = container_obj.logs()
                if isinstance(py_num, bytes):
                    py_num = float(py_num)
                    for _ in range(2):
                        # Try to remove the container two times.
                        try:
                            container_obj.remove(force=True)
                            break
                        except docker.errors.APIError:
                            print_warning(f'{log_prompt} - Could not remove the image {image}')
                    return py_num
                else:
                    raise docker.errors.ContainerError

            except Exception:
                print_warning(
                    f'{log_prompt} - Failed detecting Python version (in attempt {attempt}) for image {image}')
                continue

        return py_num
