from enum import Enum


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
