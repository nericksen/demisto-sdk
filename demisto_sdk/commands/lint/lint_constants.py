from dataclasses import dataclass
from enum import Enum
from textwrap import TextWrapper
from typing import Optional

import click


class LinterResult(Enum):
    RERUN = 0
    FAIL = 1
    SUCCESS = 2
    WARNING = 3
    FAILED_CREATING_DOCKER_IMAGE = 4


class XSOARLinterExitCode(Enum):
    SUCCESS = 0
    FAIL = 1
    PYLINT_FAILURE = 2
    WARNING = 3


@dataclass
class UnsuccessfulPackageReport:
    package_name: str
    outputs: str


@dataclass
class UnsuccessfulImageReport:
    package_name: str
    outputs: str
    image: str


@dataclass
class FailedImageCreation:
    image: str
    errors: str


@dataclass
class LintFlags:
    disable_flake8: bool
    disable_bandit: bool
    disable_mypy: bool
    disable_pylint: bool
    disable_pytest: bool
    disable_vulture: bool
    disable_xsoar_linter: bool
    disable_pwsh_analyze: bool
    disable_pwsh_test: bool
    no_coverage: bool


def print_title(sentence: str, log_color: Optional[str] = None) -> None:
    hash_tags: str = '#' * len(sentence)
    click.secho(f'{hash_tags}\n{sentence}\n{hash_tags}', fg=log_color)


def create_text_wrapper(indent: int, wrapper_name: str, preferred_width: int = 100) -> TextWrapper:
    prefix = f'{" " * indent}- {wrapper_name}'
    return TextWrapper(initial_indent=prefix, width=preferred_width, subsequent_indent=' ' * len(prefix))
