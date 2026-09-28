"""A discovered network host, initially classified as a machine."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Machine:
    ipAddress: str
    hostName: str | None = None
    site: str | None = None
    deployedComponent: list[int] = field(default_factory=list)
    createdOn: datetime | None = None
    updatedOn: datetime | None = None
    id: int | None = None
    macAddress: str | None = None
