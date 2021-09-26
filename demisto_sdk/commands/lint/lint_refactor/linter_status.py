from dataclasses import dataclass
from typing import Optional, List


@dataclass
class LinterReport:
    warnings: Optional[str]
    errors: Optional[str]
    package_name: str
    package_type: str
    images: List[str]
    exceptions: List[str]
    skipped: bool
