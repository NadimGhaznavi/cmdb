"""Application backup policy for an inventory model element."""

from dataclasses import dataclass


@dataclass
class BackupSchedule:
    modelElement: int
    enabled: bool = False
    frequency: str = "daily"
    expression: str = "0 12 * * *"
    retention: str = "1-week"
    id: int | None = None
