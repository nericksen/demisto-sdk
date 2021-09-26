from dataclasses import dataclass


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
