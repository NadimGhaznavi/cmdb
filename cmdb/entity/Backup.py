"""One application backup attempt for an inventory model element."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Backup:
    modelElement: int
    startedOn: datetime
    completedOn: datetime | None = None
    status: str = "running"
    pathname: str | None = None
    sizeBytes: int | None = None
    checksum: str | None = None
    error: str | None = None
    id: int | None = None
