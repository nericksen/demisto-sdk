from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict


class LinterResult(Enum):
    RERUN = 0
    FAIL = 1
    SUCCESS = 2
    WARNING = 4


class XSOARLinterExitCode(Enum):
    SUCCESS = 0
    FAIL = 1
    PYLINT_FAILURE = 2
    WARNING = 4


@dataclass
class UnsuccessfulPackageReport:
    package_name: str
    outputs: str
    unit_tests: list = field(default_factory=list)


class DockerImageTestReport:
    def __init__(self, linter_result: LinterResult, unit_tests: Optional[List[Dict]] = None, errors: str = ''):
        self.linter_result = linter_result
        self.unit_tests = unit_tests
        self.errors = errors

    def add_errors(self, errors: str):
        self.errors = errors
