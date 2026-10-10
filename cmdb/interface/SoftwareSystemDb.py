"""Persist manually maintained software definitions."""

from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.NamespaceDb import NamespaceDb


class SoftwareSystemDb:
    def __init__(self, db: DbMgr) -> None:
        self._db = db

    def create_application(self, name: str) -> int:
        """Create a named SoftwareSystem in the caller's transaction."""
        identity = NamespaceDb(self._db).create_package(name=name)
        self._db.execute('INSERT INTO SoftwareSystem (id) VALUES (%s)', (identity,))
        return identity

    def list_applications(self) -> list[dict]:
        """Named definitions created by Add Application are discovery targets."""
        return self._db.query(
            'SELECT MIN(ss.id) AS id, me.name FROM SoftwareSystem ss '
            'JOIN ModelElement me ON me.id = ss.id '
            'WHERE me.name IS NOT NULL GROUP BY me.name ORDER BY id')

    def list_software_systems(self) -> list[dict]:
        """Return every registered SoftwareSystem, including undeployed definitions."""
        return self._db.query(
            'SELECT ss.id, me.name, ss.type, ss.subtype, ss.supplier, ss.version '
            'FROM SoftwareSystem ss JOIN ModelElement me ON me.id = ss.id '
            'ORDER BY me.name, ss.subtype, ss.id')

    def prune_unused(self, protected: set[int]) -> list[dict]:
        """Remove undeployed systems and their components in the caller's transaction."""
        systems = self._db.query(
            'SELECT ss.id, me.name, ss.type, ss.subtype, ss.version '
            'FROM SoftwareSystem ss JOIN ModelElement me ON me.id = ss.id '
            'WHERE NOT EXISTS (SELECT 1 FROM Component c '
            'JOIN ModelElement ce ON ce.id = c.id '
            'JOIN DeployedComponent dc ON dc.component = c.id '
            'WHERE ce.namespace = ss.id) ORDER BY ss.id FOR UPDATE')
        removed = []
        for system in systems:
            if system['id'] in protected:
                continue
            self.delete_application(system['id'])
            removed.append(system)
        return removed

    def delete_application(self, identity: int) -> list[int] | None:
        """Remove one software definition in the caller's transaction.

        Keep backup targets and their components as standalone inventory for
        backup history. Return their disabled schedule IDs for cron cleanup.
        """
        if not self._db.query('SELECT id FROM SoftwareSystem WHERE id = %s FOR UPDATE', (identity,)):
            return None
        schedules = []
        components = self._db.query(
            'SELECT c.id FROM Component c JOIN ModelElement me ON me.id = c.id '
            'WHERE me.namespace = %s ORDER BY c.id FOR UPDATE', (identity,))
        for component in components:
            retained = False
            deployments = self._db.query(
                'SELECT dc.id, dm.id AS dataManager, p.id AS dataProvider, '
                'EXISTS (SELECT 1 FROM Backup b WHERE b.modelElement=dc.id) AS hasBackup, '
                'EXISTS (SELECT 1 FROM BackupSchedule bs WHERE bs.modelElement=dc.id) AS hasSchedule '
                'FROM DeployedComponent dc '
                'LEFT JOIN DataManager dm ON dm.id = dc.id '
                'LEFT JOIN DataProvider p ON p.id = dc.id '
                'WHERE dc.component = %s ORDER BY dc.id FOR UPDATE', (component['id'],))
            for deployment in deployments:
                if deployment['dataProvider'] is not None:
                    connections = self._db.query('SELECT id FROM ProviderConnection WHERE dataProvider=%s',
                                                 (deployment['id'],))
                    self._db.execute('DELETE FROM ProviderConnection WHERE dataProvider=%s', (deployment['id'],))
                    for connection in connections:
                        self._db.execute('DELETE FROM TaggedValue WHERE modelElement=%s', (connection['id'],))
                        self._db.execute('DELETE FROM ModelElement WHERE id=%s', (connection['id'],))
                    self._db.execute('DELETE FROM DataManagerDataPackage WHERE dataManager=%s', (deployment['id'],))
                    self._db.execute('DELETE FROM DataProvider WHERE id=%s', (deployment['id'],))
                    self._db.execute('DELETE FROM DataManager WHERE id=%s', (deployment['id'],))
                elif deployment['dataManager'] is not None or deployment['hasBackup'] or deployment['hasSchedule']:
                    retained = True
                    policies = self._db.query(
                        'SELECT bs.id FROM BackupSchedule bs JOIN ModelElement me ON me.id = bs.modelElement '
                        'WHERE me.namespace = %s OR me.id = %s FOR UPDATE',
                        (deployment['id'], deployment['id']))
                    for policy in policies:
                        self._db.execute('UPDATE BackupSchedule SET enabled = 0 WHERE id = %s', (policy['id'],))
                        schedules.append(policy['id'])
                    continue
                self._db.execute('DELETE FROM DeployedComponentsUsage WHERE usingComponents=%s OR usedComponents=%s',
                                 (deployment['id'], deployment['id']))
                self._db.execute('DELETE FROM DeployedComponent WHERE id = %s', (deployment['id'],))
                self._delete_parents(deployment['id'])
            if retained:
                self._db.execute('UPDATE ModelElement SET namespace = NULL WHERE id = %s', (component['id'],))
            else:
                self._db.execute('DELETE FROM Component WHERE id = %s', (component['id'],))
                self._delete_parents(component['id'])
        self._db.execute('DELETE FROM SoftwareSystem WHERE id = %s', (identity,))
        self._delete_parents(identity)
        return schedules

    def _delete_parents(self, identity: int) -> None:
        self._db.execute('DELETE FROM TaggedValue WHERE modelElement = %s', (identity,))
        self._db.execute('DELETE FROM Package WHERE id = %s', (identity,))
        self._db.execute('DELETE FROM Namespace WHERE id = %s', (identity,))
        self._db.execute('DELETE FROM ModelElement WHERE id = %s', (identity,))
