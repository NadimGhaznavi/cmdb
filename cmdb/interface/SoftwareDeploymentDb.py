"""Store OS observations through SoftwareSystem ownership and component deployment."""

from pathlib import PurePosixPath

from cmdb.entity.Component import Component
from cmdb.entity.DeployedComponent import DeployedComponent
from cmdb.entity.SoftwareSystem import SoftwareSystem
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.DataProviderDb import DataProviderDb
from cmdb.interface.NamespaceDb import NamespaceDb


class SoftwareDeploymentDb:
    def __init__(self, db: DbMgr) -> None:
        self._db = db
        self._namespaces = NamespaceDb(db)

    def list_deployments(self) -> list[dict]:
        """Project deployed software for the graph without changing the entity model."""
        deployments = self._db.query(
            "SELECT dc.id, dc.machine, dc.component, dc.pathname, ss.id AS softwareSystem, "
            "sme.name, me.name AS componentName, ss.type, ss.subtype, ss.supplier, ss.version, tv.value AS codename "
            "FROM DeployedComponent dc JOIN Component c ON c.id = dc.component "
            "JOIN ModelElement me ON me.id = c.id "
            "JOIN SoftwareSystem ss ON ss.id = me.namespace "
            "JOIN ModelElement sme ON sme.id = ss.id "
            "LEFT JOIN TaggedValue tv ON tv.modelElement = ss.id AND tv.tag = 'VERSION_CODENAME' "
            "WHERE NOT EXISTS (SELECT 1 FROM DataProvider p WHERE p.id = dc.id) "
            "ORDER BY dc.machine, dc.id"
        )

        databases = {}
        for row in self._db.query(
            "SELECT dp.dataManager, me.name FROM DataManagerDataPackage dp "
            "JOIN `Catalog` s ON s.id = dp.dataPackage "
            "JOIN ModelElement me ON me.id = s.id "
            "WHERE me.name IS NOT NULL "
            "UNION "
            "SELECT u.usingComponents AS dataManager, me.name FROM DeployedComponentsUsage u "
            "JOIN DataProvider p ON p.id = u.usedComponents "
            "JOIN DataManagerDataPackage dp ON dp.dataManager = p.id "
            "JOIN Catalog c ON c.id = dp.dataPackage JOIN ModelElement me ON me.id = c.id "
            "WHERE me.name IS NOT NULL ORDER BY dataManager, name"
        ):
            databases.setdefault(row["dataManager"], []).append(row["name"])
        for deployment in deployments:
            deployment["databases"] = databases.get(deployment["id"], [])
        return deployments

    def record_application(self, machine: int, application: int, pathname: str, version: str,
                           *, type: str | None = None, subtype: str | None = None,
                           supplier: str | None = None, codename: str | None = None,
                           components: tuple[tuple[str, str], ...] = (),
                           databases: tuple[tuple[str, str], ...] = ()) -> bool:
        """Reuse compatible releases, enriching missing metadata without erasing it."""
        definitions = self._db.query(
            'SELECT me.name FROM SoftwareSystem ss JOIN ModelElement me ON me.id = ss.id '
            'WHERE ss.id = %s FOR UPDATE', (application,))
        if not definitions:
            return False
        name = definitions[0]['name']
        releases = self._db.query(
            'SELECT ss.id, ss.version, ss.type, ss.subtype, ss.supplier, tv.value AS codename '
            'FROM SoftwareSystem ss JOIN ModelElement me ON me.id = ss.id '
            "LEFT JOIN TaggedValue tv ON tv.modelElement = ss.id AND tv.tag = 'VERSION_CODENAME' "
            'WHERE me.name = %s AND (ss.version = %s OR ss.version IS NULL) '
            'ORDER BY ss.version IS NULL, EXISTS (SELECT 1 FROM Component c '
            'JOIN ModelElement ce ON ce.id = c.id JOIN DeployedComponent dc ON dc.component = c.id '
            'WHERE ce.namespace = ss.id AND dc.machine = %s AND dc.pathname = %s) DESC, ss.id',
            (name, version, machine, pathname))
        metadata = {'type': type, 'subtype': subtype, 'supplier': supplier, 'codename': codename}
        compatible = next((row for row in releases if all(
            value is None or row[field] is None or row[field] == value
            for field, value in metadata.items())), None)
        if compatible is not None:
            release = compatible['id']
            self._db.execute(
                'UPDATE SoftwareSystem SET version = %s, type = COALESCE(type, %s), '
                'subtype = COALESCE(subtype, %s), supplier = COALESCE(supplier, %s) WHERE id = %s',
                (version, type, subtype, supplier, release))
        else:
            release = self._namespaces.create_package(name=name)
            self._db.execute(
                'INSERT INTO SoftwareSystem (id, version, type, subtype, supplier) VALUES (%s, %s, %s, %s, %s)',
                (release, version, type, subtype, supplier))
        if codename is not None and (compatible is None or compatible['codename'] is None):
            self._db.execute('INSERT INTO TaggedValue (tag, value, modelElement) VALUES (%s, %s, %s)',
                             ('VERSION_CODENAME', codename, release))
        rows = self._db.query(
            'SELECT c.id FROM Component c JOIN ModelElement me ON me.id = c.id '
            'WHERE me.namespace = %s AND me.name IS NULL ORDER BY c.id LIMIT 1', (release,))
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
            'WHERE dc.machine = %s AND dc.pathname = %s AND sme.name = %s AND me.name IS NULL '
            'ORDER BY dc.id LIMIT 1', (machine, pathname, name))
        if rows:
            identity = rows[0]['id']
            self._db.execute('UPDATE DeployedComponent SET component = %s WHERE id = %s',
                             (component, identity))
        else:
            identity = self._namespaces.create_package(namespace=machine)
            self._db.execute(
                'INSERT INTO DeployedComponent (id, pathname, machine, component) VALUES (%s, %s, %s, %s)',
                (identity, pathname, machine, component))
        for component_name, component_path in components:
            self._record_application_component(machine, release, name, component_name,
                                               str(PurePosixPath(pathname) / component_path))
        if databases:
            DataProviderDb(self._db).record_databases(machine, identity, release, pathname, databases)
        return True

    def _record_application_component(self, machine: int, release: int, application_name: str,
                                      name: str, pathname: str) -> None:
        """Reuse a named release component and a host deployment across upgrades."""
        rows = self._db.query(
            'SELECT c.id FROM Component c JOIN ModelElement me ON me.id = c.id '
            'WHERE me.namespace = %s AND me.name = %s ORDER BY c.id LIMIT 1', (release, name))
        if rows:
            component = rows[0]['id']
        else:
            component = self._namespaces.create(namespace=release, name=name)
            self._db.execute('INSERT INTO Component (id) VALUES (%s)', (component,))
        rows = self._db.query(
            'SELECT dc.id FROM DeployedComponent dc '
            'JOIN ModelElement ce ON ce.id = dc.component '
            'JOIN SoftwareSystem ss ON ss.id = ce.namespace '
            'JOIN ModelElement sme ON sme.id = ss.id '
            'WHERE dc.machine = %s AND dc.pathname = %s AND ce.name = %s AND sme.name = %s '
            'ORDER BY dc.id LIMIT 1', (machine, pathname, name, application_name))
        if rows:
            self._db.execute('UPDATE DeployedComponent SET component = %s WHERE id = %s',
                             (component, rows[0]['id']))
        else:
            identity = self._namespaces.create_package(namespace=machine, name=name)
            self._db.execute(
                'INSERT INTO DeployedComponent (id, pathname, machine, component) VALUES (%s, %s, %s, %s)',
                (identity, pathname, machine, component))

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
