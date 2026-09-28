"""Persist MariaDB deployments and the relational schemas they manage."""

from cmdb.entity.SoftwareSystem import SoftwareSystem
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.NamespaceDb import NamespaceDb
from cmdb.interface.SoftwareDeploymentDb import SoftwareDeploymentDb


class DataManagerDb:
    def __init__(self, db: DbMgr) -> None:
        self._db = db

    def record_mariadb(self, machine: int, version: str, pathname: str, databases: list[str]) -> int:
        """Upsert one observed instance and its schemas in the caller's transaction."""
        namespaces = NamespaceDb(self._db)
        component = SoftwareDeploymentDb(self._db).component_for(
            SoftwareSystem(type='DBMS', subtype='MariaDB', supplier='MariaDB', version=version))
        rows = self._db.query(
            "SELECT dm.id FROM DataManager dm JOIN DeployedComponent dc ON dc.id = dm.id "
            "JOIN Component c ON c.id = dc.component JOIN ModelElement me ON me.id = c.id "
            "JOIN SoftwareSystem ss ON ss.id = me.namespace "
            "WHERE dc.machine = %s AND BINARY dc.pathname = BINARY %s "
            "AND ss.type = 'DBMS' AND ss.subtype = 'MariaDB' ORDER BY dm.id LIMIT 1",
            (machine, pathname),
        )
        if rows:
            manager = rows[0]['id']
            self._db.execute('UPDATE DeployedComponent SET component=%s WHERE id=%s', (component.id, manager))
        else:
            manager = namespaces.create_package(namespace=machine)
            self._db.execute('INSERT INTO DeployedComponent (id, pathname, machine, component) VALUES (%s, %s, %s, %s)',
                             (manager, pathname, machine, component.id))
            self._db.execute('INSERT INTO DataManager (id) VALUES (%s)', (manager,))
        for name in dict.fromkeys(databases):
            rows = self._db.query(
                'SELECT s.id FROM `Schema` s JOIN ModelElement me ON me.id=s.id '
                'WHERE me.namespace=%s AND me.name=%s ORDER BY s.id LIMIT 1', (manager, name))
            if rows:
                identity = rows[0]['id']
            else:
                identity = namespaces.create_package(namespace=manager, name=name)
                self._db.execute('INSERT INTO `Schema` (id) VALUES (%s)', (identity,))
            self._db.execute(
                'INSERT INTO DataManagerDataPackage (dataManager, dataPackage) VALUES (%s, %s) '
                'ON DUPLICATE KEY UPDATE dataPackage=VALUES(dataPackage)', (manager, identity))
        return manager
