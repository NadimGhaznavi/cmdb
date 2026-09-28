"""A discovered network host, initially classified as a machine."""

from dataclasses import dataclass, field
from datetime import datetime

from cmdb.entity.Namespace import Namespace


@dataclass
class Machine(Namespace):
    ipAddress: str
    hostName: str | None = None
    site: str | None = None
    deployedComponent: list[int] = field(default_factory=list)
    createdOn: datetime | None = None
    updatedOn: datetime | None = None
    macAddress: str | None = None
