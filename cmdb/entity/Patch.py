"""One Debian patch-and-reboot job for an inventory machine."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Patch:
    machine: int
    address: str
    status: str = 'queued'
    createdOn: datetime | None = None
    startedOn: datetime | None = None
    rebootOn: datetime | None = None
    completedOn: datetime | None = None
    bootId: str | None = None
    output: str | None = None
    error: str | None = None
    id: int | None = None
