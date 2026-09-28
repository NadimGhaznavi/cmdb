"""A machine's enabled cron expression for patching."""

from dataclasses import dataclass


@dataclass
class PatchSchedule:
    machine: int
    enabled: bool = False
    expression: str = ''
    id: int | None = None
