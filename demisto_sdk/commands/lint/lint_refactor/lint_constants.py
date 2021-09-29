from dataclasses import dataclass
from enum import Enum


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
