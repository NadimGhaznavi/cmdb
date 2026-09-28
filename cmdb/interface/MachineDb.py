"""Persist discovered machines."""

from cmdb.entity.Machine import Machine
from cmdb.interface.DbMgr import DbMgr


class MachineDb:
    def __init__(self, db: DbMgr) -> None:
        self._db = db

    def list_machines(self) -> list[Machine]:
        rows = self._db.query(
            "SELECT ipAddress, hostName, site, deployedComponent, createdOn, updatedOn "
            "FROM machines ORDER BY INET6_ATON(ipAddress), ipAddress"
        )
        return [Machine(**row) for row in rows]

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
