import os
from dataclasses import dataclass
from typing import Optional, List, Dict, Union, Set

import click
from git import InvalidGitRepositoryError, NoSuchPathError
from wcmatch.pathlib import NEGATE, Path

from demisto_sdk.commands.common.constants import TYPE_PYTHON, TYPE_PWSH
from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.common.tools import get_all_docker_images, print_v
from demisto_sdk.commands.lint.lint_global_facts import LintGlobalFacts


@dataclass
class LintPackageFacts:
    images: List[str]
    env_vars: Dict
    lint_files: Set[Path]


def build_package_facts(lint_global_facts: LintGlobalFacts, package: Union[Script, Integration]) -> LintPackageFacts:
    log_prompt: str = f'{package.name} - Package Facts - '
    images = _get_package_images(lint_global_facts, package, log_prompt)
    return LintPackageFacts(
        images=images,
        env_vars=_get_env_vars(),
        lint_files=_get_lint_files(lint_global_facts, package, log_prompt),
    )


def _get_package_images(lint_global_facts: LintGlobalFacts, package: Union[Script, Integration],
                        log_prompt: str) -> List[str]:
    click.secho(f'{log_prompt}Pulling docker images, can take up to 1-2 minutes if not exists locally ')
    if package.script_type == TYPE_PYTHON and lint_global_facts.has_docker_engine:
        return [image for image in get_all_docker_images(script_obj=package.script)]
    return []


def _get_env_vars() -> Dict:
    return {
        'CI': os.getenv('CI', False),
        'DEMISTO_LINT_UPDATE_CERTS': os.getenv('DEMISTO_LINT_UPDATE_CERTS', 'yes')
    }


def _get_lint_files(lint_global_facts: LintGlobalFacts, package: Union[Script, Integration],
                    log_prompt: str) -> Set[Path]:
    package_dir_path: Path = package.path.parent
    lint_files: Set[Path] = set()
    if package.script_type == TYPE_PYTHON:
        lint_files = set(package_dir_path.glob(['*.py', '!__init__.py', '!*.tmp'], flags=NEGATE))
    elif package.script_type == TYPE_PWSH:
        lint_files = set(
            package_dir_path.glob(['*.ps1', '!*Tests.ps1', 'CommonServerPowerShell.ps1', 'demistomock.ps1'], flags=NEGATE))

    # Special treatment for common server packs
    if package_dir_path == 'CommonServerPython':
        lint_files.add(package_dir_path / 'CommonServerPython.py')
    elif package_dir_path == 'CommonServerPowerShell':
        lint_files.add(package_dir_path / 'CommonServerPowerShell.ps1')
    else:
        test_modules = {package_dir_path / module.name for module in lint_global_facts.test_modules.keys()}
        lint_files = lint_files.difference(test_modules)

    if not lint_files:
        click.secho(f'{log_prompt}Could not find any lint files for package {package.name}')

    # Remove files marked as tests from lint files
    unit_test_file: Optional[Path] = package.unittest_path
    if unit_test_file:
        lint_files = lint_files.difference({unit_test_file})

    return lint_files


def _remove_gitignore_files(lint_global_facts: LintGlobalFacts, lint_files: Set[Path],
                            log_prompt: str) -> Set[Path]:
    """
    Skipping files that matches gitignore patterns.
    Args:

    Returns:

    """
    if not lint_files:
        return set()
    if not lint_global_facts.content_repo:
        click.secho('Not checking gitignore because content repository was not found.', fg='yellow')
    try:
        files_to_ignore = lint_global_facts.content_repo.ignored(lint_files)
        for file in files_to_ignore:
            click.secho(f"{log_prompt} - Skipping gitignore file {file}")
        lint_files = {path for path in lint_files if path not in files_to_ignore}

    except (InvalidGitRepositoryError, NoSuchPathError):
        print_v('No gitignore files is available', log_verbose=lint_global_facts.verbose)
    return lint_files
