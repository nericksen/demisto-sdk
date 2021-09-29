import hashlib
import io
import os
import platform
import time
from abc import abstractmethod
from textwrap import TextWrapper
from typing import Tuple, Union, List, Dict

import click
import docker
import docker.errors
import docker.models.containers
import requests.exceptions
import urllib3.exceptions
from jinja2 import Environment, FileSystemLoader, exceptions
from wcmatch.pathlib import Path

from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.common.logger import Colors
from demisto_sdk.commands.common.tools import print_warning, print_v
from demisto_sdk.commands.lint.helpers import stream_docker_container_output
from demisto_sdk.commands.lint.lint_refactor.lint_constants import LinterResult, UnsuccessfulImageReport, \
    FailedImageCreation
from demisto_sdk.commands.lint.lint_refactor.lint_docker_utils import get_python_version_from_image
from demisto_sdk.commands.lint.lint_refactor.lint_global_facts import LintGlobalFacts
from demisto_sdk.commands.lint.lint_refactor.lint_package_facts import LintPackageFacts
from demisto_sdk.commands.lint.lint_refactor.linters.abstract_linters.base_linter import BaseLinter


class DockerBaseLinter(BaseLinter):
    # {package name: {image: errors}}
    FAILED_IMAGE_CREATIONS: Dict[str, List[FailedImageCreation]] = {}
    FAILED_IMAGE_TESTS: Dict[str, List[UnsuccessfulImageReport]] = {}
    WARNING_IMAGE_TESTS: Dict[str, List[UnsuccessfulImageReport]] = {}

    def __init__(self, disable_flag: bool, lint_global_facts: LintGlobalFacts, package: Union[Script, Integration],
                 lint_name: str, lint_package_facts: LintPackageFacts,
                 docker_exit_code_to_linter_results: Dict[int, Tuple[LinterResult, str, str]], env=os.environ):
        super().__init__(disable_flag, lint_global_facts, package, lint_name, lint_package_facts, env)
        self._docker_client: docker.DockerClient = docker.from_env(timeout=lint_global_facts.docker_timeout)
        self._docker_hub_login = self._docker_login()
        self.docker_exit_code_to_linter_results = docker_exit_code_to_linter_results

    @abstractmethod
    def build_linter_command(self) -> str:
        pass

    def _docker_login(self) -> bool:
        """ Login to docker-hub using environment variables:
                1. DOCKERHUB_USER - User for docker hub.
                2. DOCKERHUB_PASSWORD - Password for docker-hub.
            Used in Circle-CI for pushing into repo devtestdemisto

        Returns:
            bool: True if logged in successfully.
        """
        docker_user = os.getenv('DOCKERHUB_USER')
        docker_pass = os.getenv('DOCKERHUB_PASSWORD')
        try:
            self._docker_client.login(username=docker_user,
                                      password=docker_pass,
                                      registry='https://index.docker.io/v1')
            return self._docker_client.ping()
        except docker.errors.APIError:
            return False

    def run_on_image(self, test_image: str) -> Tuple:
        log_prompt = f'{self.package.name()} - {self.linter_name} - Image {test_image}'
        click.secho(f'{log_prompt} - Start')
        container_name = f'{self.package.name()}-{self.linter_name}'
        # Check if previous run left container a live if it do, we remove it
        self._docker_remove_container(container_name)

        # Run container
        exit_code = LinterResult.SUCCESS
        output = ''
        # test_json
        try:
            # cov = '' if no_coverage else self._pack_abs_dir.stem
            uid = os.getuid() or 4000
            print_v(f'{log_prompt} - user UID for running {self.linter_name}: {uid}', self.verbose)
            container_obj: docker.models.containers.Container = self._docker_client.containers.run(
                name=container_name,
                image=test_image,
                command=[self.build_linter_command()],
                user=f'{uid}:4000',
                detach=True,
                environment=self.lint_package_facts.env_vars
            )
            stream_docker_container_output(container_obj.logs(stream=True))
            # wait for container to finish
            container_status = container_obj.wait(condition='exited')
            # Get container exit code
            container_exit_code = container_status.get('StatusCode')
            click.secho(f'{log_prompt} - exit-code: {container_exit_code}')

            linter_result: LinterResult = self.process_docker_results(container_obj, container_exit_code, test_image)
            # Collect container logs on FAIL
            if linter_result == LinterResult.FAIL:
                output = container_obj.logs().decode('utf-8')

            # Keeping container if needed or remove it
            if self.lint_global_facts.keep_container:
                click.secho(f'{log_prompt} - container name {container_name}')
            else:
                try:
                    container_obj.remove(force=True)
                except docker.errors.NotFound as e:
                    click.secho(f'{log_prompt} - Unable to delete container - {e}', fg='red')
        except Exception as e:
            click.secho(f'{log_prompt} - Unable to run {self.linter_name}', fg='red')
            exit_code = LinterResult.RERUN
            output = str(e)

        return exit_code, output

    def process_docker_results(self, container_obj, container_exit_code, test_image: str) -> LinterResult:
        log_prompt: str = f'{self.package.name()} - {self.linter_name} - Image {test_image}'
        linter_result, log_prompt_suffix, log_color = self.docker_exit_code_to_linter_results.get(
            container_exit_code, (LinterResult.SUCCESS, ' - Successfully finished', 'green'))
        click.secho(f'{log_prompt}{log_prompt_suffix}', fg=log_color)
        return linter_result

    def run(self) -> None:
        for test_image in self.lint_package_facts.images:
            linter_result, output = LinterResult.SUCCESS, ''
            image_id, errors = '', None
            for trial in range(2):
                image_id, errors = self._docker_image_create(test_image)
                if errors:
                    # TODO handle max retries
                    continue
            if image_id and not errors:
                for trial in range(2):
                    linter_result, output = self.run_on_image(image_id)
                    if linter_result in [LinterResult.FAIL, LinterResult.SUCCESS]:
                        break
                    if linter_result == LinterResult.RERUN and trial == 1:
                        linter_result, output = LinterResult.FAIL, output
            # Error occurred building image
            else:
                failed_images: List[FailedImageCreation] = DockerBaseLinter.FAILED_IMAGE_CREATIONS[self.package.name()]
                failed_images.append(FailedImageCreation(test_image, errors))
                DockerBaseLinter.FAILED_IMAGE_CREATIONS[self.package.name()] = failed_images
            self.add_non_successful_package(linter_result, output)

    def should_run(self) -> bool:
        return all([
            self.has_docker_engine(),
            super().should_run()
        ])

    def add_docker_image_results(self, linter_result: LinterResult, errors: str, test_image: str) -> None:
        if linter_result == LinterResult.FAILED_CREATING_DOCKER_IMAGE:
            DockerBaseLinter.FAILED_IMAGE_CREATIONS[self.package.name()][test_image] = errors
        class_ = self.__class__
        package_name: str = self.package.name()
        if linter_result in [LinterResult.WARNING, LinterResult.FAIL]:
            errors, warnings, other = self.split_warnings_errors(errors)
            if warnings:
                warning_images_tests: List[UnsuccessfulImageReport] = class_.WARNING_IMAGE_TESTS.get(package_name, [])
                warning_images_tests.append(UnsuccessfulImageReport(package_name, '\n'.join(warnings), test_image))
                class_.WARNING_IMAGE_TESTS[package_name] = warning_images_tests
            error_msg = '\n'.join(errors) + '\n'.join(other)
            if error_msg:
                failed_images_tests: List[UnsuccessfulImageReport] = class_.FAILED_IMAGE_TESTS.get(package_name, [])
                failed_images_tests.append(UnsuccessfulImageReport(package_name, error_msg, test_image))
                class_.FAILED_IMAGE_TESTS[package_name] = failed_images_tests
                # TODO : in old linter, it does if errors else other. Why not take care of both anyway? check

    def has_docker_engine(self) -> bool:
        return self.lint_global_facts.has_docker_engine

    def _docker_remove_container(self, container_name: str):
        try:
            container_obj = self._docker_client.containers.get(container_name)
            container_obj.remove(force=True)
        except docker.errors.NotFound:
            pass
        except requests.exceptions.ChunkedEncodingError as err:
            # see: https://github.com/docker/docker-py/issues/2696#issuecomment-721322548
            if platform.system() != 'Darwin' or 'Connection broken' not in str(err):
                raise

    def _get_requirements(self, docker_image: str) -> List[str]:
        """
        Gets the requirements corresponding to the Python version of the docker image given.
        Args:
            docker_image (str): Docker image to get its global requirements.
        Returns:
            (List[str]): List of requirements
            - Python 2 requirements if image is Python 2 image.
            - Python 3 requirements if image is Python 3 image.
            - Empty and warning message if image is neither.
        """
        # Get requirements file for image
        python_number_from_image: float = get_python_version_from_image(docker_image)
        if 2 < python_number_from_image < 3:
            requirements = self.lint_global_facts.requirements_python2
        elif python_number_from_image > 3:
            requirements = self.lint_global_facts.requirements_python3
        else:
            requirements = []
            print_warning(f'Image: {docker_image} has unexpected python number - {python_number_from_image}')
        return requirements

    def _docker_image_create(self, docker_image: str) -> Tuple[str, str]:
        """ Create docker image:
            1. Installing 'build base' if required in alpine images version - https://wiki.alpinelinux.org/wiki/GCC
            2. Installing pypi packs - if only pylint required - only pylint installed otherwise all pytest and pylint
               installed, packages which being install can be found in path demisto_sdk/commands/lint/dev_envs
            3. The docker image build done by Dockerfile template located in
                demisto_sdk/commands/lint/templates/dockerfile.jinja2

        Args:
            docker_image (str): docker image to use as base for installing dev dependencies and python version.

        Returns:
            str, str. image name to use and errors string.
        """
        log_prompt = f'{self.package.name()} - Image create'
        test_image_id = ''

        requirements: List[str] = self._get_requirements(docker_image)
        # Using DockerFile template
        file_loader = FileSystemLoader(Path(__file__).parent / 'templates')
        env = Environment(loader=file_loader, lstrip_blocks=True, trim_blocks=True, autoescape=True)
        template = env.get_template('dockerfile.jinja2')
        try:
            # TODO - maybe add test requirements, was removed, see if needed
            dockerfile = template.render(image=docker_image, pypi_packs=requirements,
                                         pack_type=self.package.script_type, copy_pack=False)
        except exceptions.TemplateError as e:
            print_v(f'{log_prompt} - Error when build image - {e.message()}', self.lint_global_facts.verbose)
            return test_image_id, str(e)
        # Trying to pull image based on dockerfile hash, will check if something changed
        errors = ""
        test_image_name = f'devtest{docker_image}-{hashlib.md5(dockerfile.encode("utf-8")).hexdigest()}'
        test_image = None
        try:
            # TODO color
            click.secho(f'{log_prompt} - Trying to pull existing image {test_image_name}', fg='green')
            test_image = self._docker_client.images.pull(test_image_name)
        except (docker.errors.APIError, docker.errors.ImageNotFound):
            click.secho(f"{log_prompt} - Unable to find image {test_image_name}")
        # Creating new image if existing image isn't found
        if not test_image:
            try:
                self.create_new_image(log_prompt, docker_image, test_image_name, dockerfile)
            except (docker.errors.BuildError, docker.errors.APIError, Exception) as e:
                click.secho(f'{log_prompt} - Build errors occurred {e}', fg='red')
                errors = str(e)
        else:
            click.secho(f"{log_prompt} - Found existing image {test_image_name}")
        self.build_docker(log_prompt, test_image_name, template)
        if test_image_id:
            click.secho(f"{log_prompt} - Image {test_image_id} created successfully")

        return test_image_name, errors

    def create_new_image(self, log_prompt: str, docker_image: str, test_image_name: str, dockerfile):
        click.secho(f'{log_prompt} - Creating image based on {docker_image} - Could take 2-3 minutes at first time')
        with io.BytesIO() as f:
            f.write(dockerfile.encode('utf-8'))
            f.seek(0)
            self._docker_client.images.build(fileobj=f, tag=test_image_name, forcerm=True)
            if self._docker_hub_login:
                for trial in range(2):
                    try:
                        self._docker_client.images.push(test_image_name)
                        click.secho(f'{log_prompt} - Image {test_image_name} pushed to repository')
                        break
                    except (requests.exceptions.ConnectionError, urllib3.exceptions.ReadTimeoutError,
                            requests.exceptions.ReadTimeout):
                        click.secho(f'{log_prompt} - Unable to push image {test_image_name} to repository')

    def build_docker(self, log_prompt: str, test_image_name: str, template):
        dockerfile_path = Path(self.package.path / '.Dockerfile')
        dockerfile = template.render(image=test_image_name, copy_pack=True)
        with open(dockerfile_path, mode="w+") as file:
            file.write(str(dockerfile))
        # we only do retries in CI env where docker build is sometimes flacks
        build_tries = int(os.getenv('DEMISTO_SDK_DOCKER_BUILD_TRIES', 3)) if os.getenv('CI') else 1
        for trial in range(build_tries):
            try:
                click.secho(f'{log_prompt} - Copy pack dir to image {test_image_name}')
                docker_image_final = self._docker_client.images.build(path=str(dockerfile_path.parent),
                                                                      dockerfile=dockerfile_path.stem,
                                                                      forcerm=True)
                test_image_name = docker_image_final[0].short_id
                break
            except Exception as e:
                click.secho(f'{log_prompt} - errors occurred when building image in dir {e}', fg='red')
                if trial >= build_tries:
                    errors = str(e)
                else:
                    click.secho(f'{log_prompt} - sleeping 2 seconds and will retry build after')
                    time.sleep(2)
        if dockerfile_path.exists():
            dockerfile_path.unlink()

    @classmethod
    def report_unsuccessful_lint_check(cls, linter_name: str):
        def _report_unsuccessful(image_results: Dict[str, List[UnsuccessfulImageReport]],
                                 title_suffix: str, log_color: str):
            if not image_results:
                return
            sentence = f'{linter_name} {title_suffix}'
            hash_tags: str = '#' * len(sentence)
            click.secho(f'\n{hash_tags}\n{sentence}\n{hash_tags}', fg=log_color)
            for package_name, image_reports in image_results.items():
                click.secho(f'{package_name}', fg='red')
                for unsuccessful_report in image_reports:
                    click.secho(f'Image - {unsuccessful_report.image}:\n{title_suffix}:\n{unsuccessful_report.outputs}')

        _report_unsuccessful(cls.FAILED_IMAGE_TESTS, 'Errors', 'red')
        _report_unsuccessful(cls.WARNING_IMAGE_TESTS, 'Warnings', 'yellow')

    @staticmethod
    def report_unsuccessful_image_creations() -> None:
        if not DockerBaseLinter.FAILED_IMAGE_CREATIONS:
            return
        # Indentation config
        wrapper_pack: TextWrapper = BaseLinter.create_text_wrapper(2, 'Package:')
        wrapper_image: TextWrapper = BaseLinter.create_text_wrapper(2, 'Image:')
        wrapper_error: TextWrapper = BaseLinter.create_text_wrapper(4, 'Error:')
        sentence = " Image Creation Errors "
        hash_tags: str = '#' * len(sentence)
        click.secho(f'{hash_tags}\n{sentence}\n{hash_tags}', fg='red')
        for package_name, failed_creations in DockerBaseLinter.FAILED_IMAGE_CREATIONS.items():
            click.secho(wrapper_pack.fill(f'{Colors.Fg.cyan}{package_name}{Colors.reset}'))
            for failed_image_creation in failed_creations:
                click.secho(wrapper_image.fill(failed_image_creation.image))
                click.secho(wrapper_error.fill(failed_image_creation.errors))
