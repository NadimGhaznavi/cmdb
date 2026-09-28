"""Application backup policy for an inventory model element."""

from dataclasses import dataclass


@dataclass
class BackupSchedule:
    modelElement: int
    enabled: bool = False
    frequency: str = "daily"
    retention: str = "1-week"
    id: int | None = None
