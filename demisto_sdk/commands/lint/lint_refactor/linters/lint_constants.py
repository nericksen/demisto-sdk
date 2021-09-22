from enum import Enum


class LinterResult(Enum):
    RERUN = 0
    FAIL = 1
    SUCCESS = 2
