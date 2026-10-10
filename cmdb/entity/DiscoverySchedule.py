"""Application policy for periodic discovery of the configured network."""

from dataclasses import dataclass

from cmdb.constants.DCMDB import DCMDB


@dataclass
class DiscoverySchedule:
    enabled: bool = False
    expression: str = DCMDB.DISCOVERY_CRON
    id: int = 1
