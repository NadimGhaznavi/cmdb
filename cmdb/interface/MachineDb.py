"""Persist discovered machines."""

from cmdb.entity.Machine import Machine
from cmdb.entity.TaggedValue import TaggedValue
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.NamespaceDb import NamespaceDb


class MachineDb:
    def __init__(self, db: DbMgr) -> None:
        self._db = db

    def list_machines(self) -> list[Machine]:
        rows = self._db.query(
            "SELECT m.id, me.name, me.namespace, ipAddress, hostName, macAddress, site, createdOn, updatedOn "
            "FROM Machine m JOIN ModelElement me ON me.id = m.id ORDER BY INET6_ATON(ipAddress), ipAddress"
        )
        return self._with_deployments(rows)

    def _with_deployments(self, rows: list[dict]) -> list[Machine]:
        machines = [Machine(**row) for row in rows]
        if machines:
            by_id = {machine.id: machine for machine in machines}
            placeholders = ", ".join("%s" for _ in machines)
            deployments = self._db.query(
                f"SELECT id, machine FROM DeployedComponent WHERE machine IN ({placeholders}) ORDER BY id",
                tuple(by_id),
            )
            elements = self._db.query(
                f"SELECT id, namespace FROM ModelElement WHERE namespace IN ({placeholders}) ORDER BY id",
                tuple(by_id),
            )
            for element in elements:
                by_id[element["namespace"]].ownedElement.append(element["id"])
            for deployment in deployments:
                by_id[deployment["machine"]].deployedComponent.append(deployment["id"])
            tags = self._db.query(
                f"SELECT id, tag, value, modelElement FROM TaggedValue "
                f"WHERE modelElement IN ({placeholders}) ORDER BY id", tuple(by_id),
            )
            for tag in tags:
                by_id[tag["modelElement"]].taggedValue.append(TaggedValue(**tag))
        return machines

    def update_environment(self, machine_id: int, environment: str) -> bool:
        """Save the machine's inherited tag; unclassified means no tag."""
        if environment not in ('dev', 'qa', 'prod', 'unclassified'):
            raise ValueError('Invalid deployment environment.')
        with self._db.transaction():
            rows = self._db.query('SELECT id FROM Machine WHERE id = %s FOR UPDATE', (machine_id,))
            if not rows:
                return False
            if environment == 'unclassified':
                self._db.execute(
                    'DELETE FROM TaggedValue WHERE modelElement = %s AND tag = %s',
                    (machine_id, 'DeploymentEnvironment'),
                )
            else:
                self._db.execute(
                    'INSERT INTO TaggedValue (modelElement, tag, value) VALUES (%s, %s, %s) '
                    'ON DUPLICATE KEY UPDATE value = VALUES(value)',
                    (machine_id, 'DeploymentEnvironment', environment),
                )
        return True

    def upsert(self, machine: Machine) -> int:
        """Refresh discovery fields and return the stable machine ID."""
        rows = self._db.query("SELECT id FROM Machine WHERE ipAddress = %s", (machine.ipAddress,))
        if rows:
            identity = rows[0]["id"]
            self._db.execute(
                "UPDATE Machine SET macAddress = COALESCE(%s, macAddress), "
                "updatedOn = CURRENT_TIMESTAMP(6) WHERE id = %s", (machine.macAddress, identity),
            )
        else:
            identity = NamespaceDb(self._db).create()
            self._db.execute(
                "INSERT INTO Machine (id, ipAddress, hostName, site, macAddress) VALUES (%s, %s, %s, %s, %s)",
                (identity, machine.ipAddress, machine.hostName, machine.site, machine.macAddress),
            )
        return identity

    def update_discovered_hostname(self, machine_id: int, host_name: str) -> None:
        """Store the hostname reported over SSH using the stable machine identity."""
        self._db.execute(
            "UPDATE Machine SET hostName = %s, updatedOn = CURRENT_TIMESTAMP(6) WHERE id = %s",
            (host_name, machine_id),
        )

    def update_discovered_mac(self, machine_id: int, mac_address: str) -> None:
        """Store the address of the interface owning the discovered IP."""
        self._db.execute(
            "UPDATE Machine SET macAddress = %s, updatedOn = CURRENT_TIMESTAMP(6) WHERE id = %s",
            (mac_address, machine_id),
        )

    def update_hostname(self, ip_address: str, host_name: str | None) -> Machine | None:
        with self._db.transaction():
            self._db.execute(
                "UPDATE Machine SET hostName = %s, updatedOn = CURRENT_TIMESTAMP(6) "
                "WHERE ipAddress = %s", (host_name, ip_address),
            )
            rows = self._db.query(
                "SELECT m.id, me.name, me.namespace, ipAddress, hostName, macAddress, site, createdOn, updatedOn "
                "FROM Machine m JOIN ModelElement me ON me.id = m.id WHERE ipAddress = %s", (ip_address,),
            )
            machines = self._with_deployments(rows)
        return machines[0] if machines else None
