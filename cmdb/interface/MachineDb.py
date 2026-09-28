"""Persist discovered machines."""

from cmdb.entity.Machine import Machine
from cmdb.interface.DbMgr import DbMgr


class MachineDb:
    def __init__(self, db: DbMgr) -> None:
        self._db = db

    def upsert(self, machine: Machine) -> None:
        """Refresh discovery fields while preserving manually assigned values."""
        self._db.execute(
            "INSERT INTO machines (ipAddress, hostName, site, deployedComponent) "
            "VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE "
            "hostName = COALESCE(VALUES(hostName), hostName), "
            "updatedOn = CURRENT_TIMESTAMP(6)",
            (machine.ipAddress, machine.hostName, machine.site, machine.deployedComponent),
        )
