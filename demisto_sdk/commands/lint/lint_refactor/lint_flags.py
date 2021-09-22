from dataclasses import dataclass


@dataclass
class LintFlags:
    disable_flake8: bool
