"""Persist discovered machines."""

from cmdb.entity.Machine import Machine
from cmdb.interface.DbMgr import DbMgr


class MachineDb:
    def __init__(self, db: DbMgr) -> None:
        self._db = db

    def list_machines(self) -> list[Machine]:
        rows = self._db.query(
            "SELECT id, ipAddress, hostName, macAddress, site, createdOn, updatedOn "
            "FROM machines ORDER BY INET6_ATON(ipAddress), ipAddress"
        )
        return self._with_deployments(rows)

    def _with_deployments(self, rows: list[dict]) -> list[Machine]:
        machines = [Machine(**row) for row in rows]
        if machines:
            by_id = {machine.id: machine for machine in machines}
            placeholders = ", ".join("%s" for _ in machines)
            deployments = self._db.query(
                f"SELECT id, machine FROM deployedComponents WHERE machine IN ({placeholders}) ORDER BY id",
                tuple(by_id),
            )
            for deployment in deployments:
                by_id[deployment["machine"]].deployedComponent.append(deployment["id"])
        return machines

    def upsert(self, machine: Machine) -> int:
        """Refresh discovery fields and return the stable machine ID."""
        return self._db.insert(
            "INSERT INTO machines (ipAddress, hostName, site, macAddress) "
            "VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE "
            "id = LAST_INSERT_ID(id), "
            "macAddress = COALESCE(VALUES(macAddress), macAddress), "
            "updatedOn = CURRENT_TIMESTAMP(6)",
            (machine.ipAddress, machine.hostName, machine.site, machine.macAddress),
        )

    def update_hostname(self, ip_address: str, host_name: str | None) -> Machine | None:
        with self._db.transaction():
            self._db.execute(
                "UPDATE machines SET hostName = %s, updatedOn = CURRENT_TIMESTAMP(6) "
                "WHERE ipAddress = %s", (host_name, ip_address),
            )
            rows = self._db.query(
                "SELECT id, ipAddress, hostName, macAddress, site, createdOn, updatedOn "
                "FROM machines WHERE ipAddress = %s", (ip_address,),
            )
            machines = self._with_deployments(rows)
        return machines[0] if machines else None
