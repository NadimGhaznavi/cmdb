"""Connect application clients to observed MariaDB catalogs on the same machine."""

from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.NamespaceDb import NamespaceDb


class DataProviderDb:
    def __init__(self, db: DbMgr) -> None:
        self._db = db

    def record_databases(self, machine: int, application: int, release: int, pathname: str,
                         databases: tuple[tuple[str, str], ...]) -> None:
        """Upsert verified connections in the caller's application transaction."""
        matches = []
        for label, catalog in databases:
            for row in self._db.query(
                'SELECT dm.id AS manager, ca.id AS catalog FROM DataManager dm '
                'JOIN DeployedComponent dc ON dc.id=dm.id '
                'JOIN ModelElement ce ON ce.id=dc.component '
                'JOIN SoftwareSystem ss ON ss.id=ce.namespace '
                'JOIN DataManagerDataPackage dp ON dp.dataManager=dm.id '
                'JOIN Catalog ca ON ca.id=dp.dataPackage JOIN ModelElement me ON me.id=ca.id '
                "WHERE dc.machine=%s AND ss.type='DBMS' AND ss.subtype='MariaDB' "
                'AND BINARY me.name=BINARY %s ORDER BY dm.id', (machine, catalog)):
                matches.append((label, row['manager'], row['catalog']))
        if not matches:
            return
        namespaces = NamespaceDb(self._db)
        rows = self._db.query(
            'SELECT c.id FROM Component c JOIN ModelElement me ON me.id=c.id '
            "WHERE me.namespace=%s AND me.name='MariaDB Client' ORDER BY c.id LIMIT 1", (release,))
        if rows:
            component = rows[0]['id']
        else:
            component = namespaces.create(namespace=release, name='MariaDB Client')
            self._db.execute('INSERT INTO Component (id) VALUES (%s)', (component,))
        rows = self._db.query(
            'SELECT p.id FROM DataProvider p JOIN DeployedComponentsUsage u ON u.usedComponents=p.id '
            'WHERE u.usingComponents=%s ORDER BY p.id LIMIT 1', (application,))
        if rows:
            provider = rows[0]['id']
            self._db.execute('UPDATE DeployedComponent SET component=%s WHERE id=%s', (component, provider))
        else:
            provider = namespaces.create_package(namespace=machine, name='MariaDB Client')
            self._db.execute('INSERT INTO DeployedComponent (id, pathname, machine, component) VALUES (%s,%s,%s,%s)',
                             (provider, pathname, machine, component))
            self._db.execute('INSERT INTO DataManager (id) VALUES (%s)', (provider,))
            self._db.execute('INSERT INTO DataProvider (id) VALUES (%s)', (provider,))
            self._db.execute('INSERT INTO DeployedComponentsUsage (usingComponents, usedComponents) VALUES (%s,%s)',
                             (application, provider))
        for label, manager, catalog in matches:
            rows = self._db.query(
                'SELECT pc.id FROM ProviderConnection pc JOIN ModelElement me ON me.id=pc.id '
                'WHERE pc.dataProvider=%s AND pc.dataManager=%s AND me.name=%s LIMIT 1',
                (provider, manager, label))
            if not rows:
                connection = self._db.insert('INSERT INTO ModelElement (namespace, name) VALUES (%s,%s)',
                                             (provider, label))
                self._db.execute('INSERT INTO ProviderConnection (id, dataProvider, dataManager) VALUES (%s,%s,%s)',
                                 (connection, provider, manager))
            self._db.execute(
                'INSERT INTO DataManagerDataPackage (dataManager, dataPackage) VALUES (%s,%s) '
                'ON DUPLICATE KEY UPDATE dataPackage=VALUES(dataPackage)', (provider, catalog))
