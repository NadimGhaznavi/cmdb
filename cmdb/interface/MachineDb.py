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
            "updatedOn = CURRENT_TIMESTAMP(6)",
            (machine.ipAddress, machine.hostName, machine.site, machine.deployedComponent),
        )

    def update_hostname(self, ip_address: str, host_name: str | None) -> Machine | None:
        with self._db.transaction():
            self._db.execute(
                "UPDATE machines SET hostName = %s, updatedOn = CURRENT_TIMESTAMP(6) "
                "WHERE ipAddress = %s", (host_name, ip_address),
            )
            rows = self._db.query(
                "SELECT ipAddress, hostName, site, deployedComponent, createdOn, updatedOn "
                "FROM machines WHERE ipAddress = %s", (ip_address,),
            )
        return Machine(**rows[0]) if rows else None
