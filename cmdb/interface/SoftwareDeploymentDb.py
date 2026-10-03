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
        deployments = self._db.query(
            "SELECT dc.id, dc.machine, dc.component, dc.pathname, ss.id AS softwareSystem, "
            "sme.name, ss.type, ss.subtype, ss.supplier, ss.version, tv.value AS codename "
            "FROM DeployedComponent dc JOIN Component c ON c.id = dc.component "
            "JOIN ModelElement me ON me.id = c.id "
            "JOIN SoftwareSystem ss ON ss.id = me.namespace "
            "JOIN ModelElement sme ON sme.id = ss.id "
            "LEFT JOIN TaggedValue tv ON tv.modelElement = ss.id AND tv.tag = 'VERSION_CODENAME' "
            "ORDER BY dc.machine, dc.id"
        )

        databases = {}
        for row in self._db.query(
            "SELECT dp.dataManager, me.name FROM DataManagerDataPackage dp "
            "JOIN `Schema` s ON s.id = dp.dataPackage "
            "JOIN ModelElement me ON me.id = s.id "
            "WHERE me.name IS NOT NULL ORDER BY dp.dataManager, me.name"
        ):
            databases.setdefault(row["dataManager"], []).append(row["name"])
        for deployment in deployments:
            deployment["databases"] = databases.get(deployment["id"], [])
        return deployments

    def record_application(self, machine: int, application: int, pathname: str, version: str) -> bool:
        """Record an installation, or skip a definition deleted since discovery began."""
        definitions = self._db.query(
            'SELECT me.name FROM SoftwareSystem ss JOIN ModelElement me ON me.id = ss.id '
            'WHERE ss.id = %s FOR UPDATE', (application,))
        if not definitions:
            return False
        name = definitions[0]['name']
        releases = self._db.query(
            'SELECT ss.id, ss.version FROM SoftwareSystem ss JOIN ModelElement me ON me.id = ss.id '
            'WHERE me.name = %s AND ss.type IS NULL AND (ss.version = %s OR ss.version IS NULL) '
            'ORDER BY ss.version IS NULL, ss.id LIMIT 1', (name, version))
        if releases:
            release = releases[0]['id']
            if releases[0]['version'] is None:
                self._db.execute('UPDATE SoftwareSystem SET version = %s WHERE id = %s', (version, release))
        else:
            release = self._namespaces.create_package(name=name)
            self._db.execute('INSERT INTO SoftwareSystem (id, version) VALUES (%s, %s)', (release, version))
        rows = self._db.query(
            'SELECT c.id FROM Component c JOIN ModelElement me ON me.id = c.id '
            'WHERE me.namespace = %s ORDER BY c.id LIMIT 1', (release,))
        if rows:
            component = rows[0]['id']
        else:
            component = self._namespaces.create(namespace=release)
            self._db.execute('INSERT INTO Component (id) VALUES (%s)', (component,))
        rows = self._db.query(
            'SELECT dc.id FROM DeployedComponent dc '
            'JOIN Component c ON c.id = dc.component JOIN ModelElement me ON me.id = c.id '
            'JOIN SoftwareSystem ss ON ss.id = me.namespace '
            'JOIN ModelElement sme ON sme.id = ss.id '
            'WHERE dc.machine = %s AND dc.pathname = %s AND sme.name = %s AND ss.type IS NULL '
            'ORDER BY dc.id LIMIT 1', (machine, pathname, name))
        if rows:
            self._db.execute('UPDATE DeployedComponent SET component = %s WHERE id = %s',
                             (component, rows[0]['id']))
        else:
            identity = self._namespaces.create_package(namespace=machine)
            self._db.execute(
                'INSERT INTO DeployedComponent (id, pathname, machine, component) VALUES (%s, %s, %s, %s)',
                (identity, pathname, machine, component))
        return True

    def debian_hosts(self) -> list[dict]:
        """List machines whose deployed operating system is identified as Debian."""
        return self._db.query(
            "SELECT DISTINCT m.id, m.hostName, m.ipAddress FROM Machine m "
            "JOIN DeployedComponent dc ON dc.machine=m.id "
            "JOIN Component c ON c.id=dc.component JOIN ModelElement me ON me.id=c.id "
            "JOIN SoftwareSystem ss ON ss.id=me.namespace "
            "WHERE dc.pathname='/' AND ss.type='linux' AND ss.subtype='debian' "
            "ORDER BY m.hostName, m.ipAddress")

    def record_operating_system(self, machine: int, system: SoftwareSystem) -> None:
        """Refresh the scanner's OS deployment at / within the caller's transaction.

        Definitions are shared; deployments belong to individual machines.
        The single scanner worker serializes discovery writes.
        """
        if system.type not in ("OS", "linux") or not system.subtype:
            raise ValueError("An operating system classification is required.")
        component = self.component_for(system)

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
                                           namespace=machine, id=self._namespaces.create_package(namespace=machine))
            self._db.execute(
                "INSERT INTO DeployedComponent (id, pathname, machine, component) VALUES (%s, %s, %s, %s)",
                (deployment.id, deployment.pathname, deployment.machine, deployment.component),
            )

    def component_for(self, system: SoftwareSystem) -> Component:
        """Reuse a software release and its component within the caller transaction."""
        tags = {tag.tag: tag.value for tag in system.taggedValue}
        if len(tags) != len(system.taggedValue) or set(tags) - {"VERSION_CODENAME"}:
            raise ValueError("Software observations support one VERSION_CODENAME tag.")
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
            system.id = self._namespaces.create_package()
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

        return component
