"""Store OS observations through SoftwareSystem ownership and component deployment."""

from cmdb.entity.Component import Component
from cmdb.entity.DeployedComponent import DeployedComponent
from cmdb.entity.SoftwareSystem import SoftwareSystem
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.NamespaceDb import NamespaceDb


class SoftwareDeploymentDb:
    def __init__(self, db: DbMgr) -> None:
        self._db = db
        self._namespaces = NamespaceDb(db)

    def list_deployments(self) -> list[dict]:
        """Project deployed software for the graph without changing the entity model."""
        return self._db.query(
            "SELECT dc.id, dc.machine, dc.component, dc.pathname, ss.id AS softwareSystem, "
            "ss.type, ss.subtype, ss.supplier, ss.version, tv.value AS codename "
            "FROM DeployedComponent dc JOIN Component c ON c.id = dc.component "
            "JOIN ModelElement me ON me.id = c.id "
            "JOIN SoftwareSystem ss ON ss.id = me.namespace "
            "LEFT JOIN TaggedValue tv ON tv.modelElement = ss.id AND tv.tag = 'VERSION_CODENAME' "
            "ORDER BY dc.machine, dc.id"
        )

    def record_operating_system(self, machine: int, system: SoftwareSystem) -> None:
        """Refresh the scanner's OS deployment at / within the caller's transaction.

        Definitions are shared; deployments belong to individual machines.
        The single scanner worker serializes discovery writes.
        """
        if system.type not in ("OS", "linux") or not system.subtype:
            raise ValueError("An operating system classification is required.")
        tags = {tag.tag: tag.value for tag in system.taggedValue}
        if len(tags) != len(system.taggedValue) or set(tags) - {"VERSION_CODENAME"}:
            raise ValueError("OS observations support one VERSION_CODENAME tag.")
        rows = self._db.query(
            "SELECT ss.id, tv.id AS taggedValueId FROM SoftwareSystem ss LEFT JOIN TaggedValue tv "
            "ON tv.modelElement = ss.id AND tv.tag = 'VERSION_CODENAME' "
            "WHERE ss.type <=> %s AND ss.subtype <=> %s "
            "AND ss.supplier <=> %s AND ss.version <=> %s AND tv.value <=> %s "
            "ORDER BY ss.id LIMIT 1",
            (system.type, system.subtype, system.supplier, system.version, tags.get("VERSION_CODENAME")),
        )
        if rows:
            system.id = rows[0]["id"]
            for tag in system.taggedValue:
                tag.modelElement = system.id
                tag.id = rows[0]["taggedValueId"]
        else:
            system.id = self._namespaces.create()
            self._db.execute(
                "INSERT INTO SoftwareSystem (id, type, subtype, supplier, version) VALUES (%s, %s, %s, %s, %s)",
                (system.id, system.type, system.subtype, system.supplier, system.version),
            )
            for tag in system.taggedValue:
                tag.modelElement = system.id
                tag.id = self._db.insert(
                    "INSERT INTO TaggedValue (tag, value, modelElement) VALUES (%s, %s, %s)",
                    (tag.tag, tag.value, tag.modelElement),
                )

        # Component.namespace is inherited from ModelElement, not stored on Component.
        rows = self._db.query(
            "SELECT c.id FROM Component c JOIN ModelElement me ON me.id = c.id "
            "WHERE me.namespace = %s ORDER BY c.id LIMIT 1", (system.id,),
        )
        component = Component(namespace=system.id)
        if rows:
            component.id = rows[0]["id"]
        else:
            component.id = self._namespaces.create(namespace=system.id)
            self._db.execute("INSERT INTO Component (id) VALUES (%s)", (component.id,))

        rows = self._db.query(
            "SELECT dc.id FROM DeployedComponent dc "
            "JOIN Component c ON c.id = dc.component "
            "JOIN ModelElement me ON me.id = c.id "
            "JOIN SoftwareSystem ss ON ss.id = me.namespace "
            "WHERE dc.machine = %s AND dc.pathname = '/' AND ss.type IN ('OS', 'linux') "
            "ORDER BY dc.id LIMIT 1", (machine,),
        )
        if rows:
            self._db.execute("UPDATE DeployedComponent SET component = %s WHERE id = %s",
                             (component.id, rows[0]["id"]))
        else:
            deployment = DeployedComponent(pathname="/", machine=machine, component=component.id,
                                           namespace=machine, id=self._namespaces.create(namespace=machine))
            self._db.execute(
                "INSERT INTO DeployedComponent (id, pathname, machine, component) VALUES (%s, %s, %s, %s)",
                (deployment.id, deployment.pathname, deployment.machine, deployment.component),
            )
