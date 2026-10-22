"""One application-owned backup source snapshot and attempt outcome."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Backup:
    modelElement: int | None
    startedOn: datetime
    kind: str
    ipAddress: str
    sourcePathname: str
    hostName: str | None = None
    macAddress: str | None = None
    environment: str | None = None
    site: str | None = None
    databaseName: str | None = None
    applicationName: str | None = None
    componentName: str | None = None
    softwareName: str | None = None
    softwareVersion: str | None = None
    completedOn: datetime | None = None
    status: str = "running"
    pathname: str | None = None
    sizeBytes: int | None = None
    checksum: str | None = None
    error: str | None = None
    id: int | None = None
