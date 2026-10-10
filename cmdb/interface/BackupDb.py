"""Backup inventory lookup and attempt persistence."""

from cmdb.interface.DbMgr import DbMgr


class BackupDb:
    def __init__(self, db: DbMgr) -> None:
        self._db = db

    def databases(self) -> list[dict]:
        return self._db.query(
            "SELECT s.id AS modelElement, me.name AS databaseName, m.hostName, m.ipAddress, "
            "m.id AS machine, bs.id AS scheduleId, COALESCE(bs.enabled, 0) AS enabled, "
            "COALESCE(bs.expression, '0 12 * * *') AS expression, COALESCE(bs.retention, '1-week') AS retention, "
            "(SELECT MAX(b.completedOn) FROM Backup b WHERE b.modelElement=s.id "
            "AND b.status='succeeded') AS lastBackup, "
            "(SELECT b.id FROM Backup b WHERE b.modelElement=s.id ORDER BY b.id DESC LIMIT 1) AS latestBackup "
            "FROM `Catalog` s JOIN ModelElement me ON me.id=s.id "
            "JOIN DataManager dm ON dm.id=me.namespace JOIN DeployedComponent dc ON dc.id=dm.id "
            "JOIN DataManagerDataPackage dp ON dp.dataManager=dm.id AND dp.dataPackage=s.id "
            "JOIN Machine m ON m.id=dc.machine JOIN Component c ON c.id=dc.component "
            "JOIN ModelElement cm ON cm.id=c.id JOIN SoftwareSystem ss ON ss.id=cm.namespace "
            "LEFT JOIN BackupSchedule bs ON bs.modelElement=s.id "
            "WHERE ss.type='DBMS' AND ss.subtype='MariaDB' "
            "AND LOWER(me.name) NOT IN ('mysql', 'information_schema', 'performance_schema', 'sys') "
            "ORDER BY m.id, me.name")

    def hosts(self) -> list[dict]:
        return self._db.query(
            "SELECT DISTINCT m.id AS machine, m.hostName, m.ipAddress FROM DataManager dm "
            "JOIN DeployedComponent dc ON dc.id=dm.id JOIN Machine m ON m.id=dc.machine "
            "JOIN Component c ON c.id=dc.component JOIN ModelElement me ON me.id=c.id "
            "JOIN SoftwareSystem ss ON ss.id=me.namespace WHERE ss.type='DBMS' AND ss.subtype='MariaDB'")

    def components(self) -> list[dict]:
        """Declared filesystem deployments, excluding install roots and DB clients."""
        return self._db.query(
            "SELECT dc.id AS modelElement, 'directory' AS kind, ce.name AS componentName, "
            "ae.name AS applicationName, ss.id AS application, dc.pathname, m.id AS machine, "
            "m.hostName, m.ipAddress, bs.id AS scheduleId, COALESCE(bs.enabled, 0) AS enabled, "
            "COALESCE(bs.expression, '0 12 * * *') AS expression, "
            "COALESCE(bs.retention, '1-week') AS retention, "
            "(SELECT MAX(b.completedOn) FROM Backup b WHERE b.modelElement=dc.id "
            "AND b.status='succeeded') AS lastBackup, "
            "(SELECT b.id FROM Backup b WHERE b.modelElement=dc.id ORDER BY b.id DESC LIMIT 1) AS latestBackup "
            "FROM DeployedComponent dc JOIN Component c ON c.id=dc.component "
            "JOIN ModelElement ce ON ce.id=c.id JOIN SoftwareSystem ss ON ss.id=ce.namespace "
            "JOIN ModelElement ae ON ae.id=ss.id JOIN Machine m ON m.id=dc.machine "
            "LEFT JOIN BackupSchedule bs ON bs.modelElement=dc.id "
            "WHERE ce.name IS NOT NULL AND NOT EXISTS (SELECT 1 FROM DataManager dm WHERE dm.id=dc.id) "
            "ORDER BY m.id, ae.name, ce.name, dc.pathname")

    def applications(self) -> list[dict]:
        rows = self.components()
        databases = {row['modelElement']: row for row in self.databases()}
        for link in self._db.query(
            "SELECT DISTINCT ae.name AS applicationName, ss.id AS application, "
            "dc.machine, ca.id AS modelElement FROM DataProvider p "
            "JOIN DeployedComponentsUsage u ON u.usedComponents=p.id "
            "JOIN DeployedComponent dc ON dc.id=u.usingComponents "
            "JOIN ModelElement ce ON ce.id=dc.component JOIN SoftwareSystem ss ON ss.id=ce.namespace "
            "JOIN ModelElement ae ON ae.id=ss.id "
            "JOIN DataManagerDataPackage dp ON dp.dataManager=p.id JOIN Catalog ca ON ca.id=dp.dataPackage "
            "ORDER BY dc.machine, ae.name, ca.id"):
            database = databases.get(link['modelElement'])
            if database is not None and database['machine'] == link['machine']:
                rows.append(dict(database, **link, kind='database'))
        return rows

    def target(self, identity: int) -> dict | None:
        for lookup in (self.databases, self.components):
            for row in lookup():
                if row['modelElement'] == identity:
                    return row
        return None

    def get(self, identity: int) -> dict | None:
        rows = self._db.query('SELECT * FROM Backup WHERE id=%s', (identity,))
        return rows[0] if rows else None

    def files(self) -> list[dict]:
        """Successful database dumps and directory archives, newest first."""
        return self._db.query(
            "SELECT b.id, b.completedOn AS backupTime, "
            "TIMESTAMPDIFF(SECOND, b.startedOn, b.completedOn) AS elapsedSeconds, me.name AS databaseName, "
            "m.hostName, m.ipAddress, b.pathname, b.sizeBytes FROM Backup b "
            "JOIN ModelElement target ON target.id=b.modelElement "
            "LEFT JOIN `Catalog` s ON s.id=target.id "
            "JOIN DeployedComponent dc ON dc.id=CASE WHEN s.id IS NOT NULL THEN target.namespace ELSE target.id END "
            "JOIN ModelElement me ON me.id=CASE WHEN s.id IS NOT NULL THEN s.id ELSE dc.component END "
            "JOIN Machine m ON m.id=dc.machine WHERE b.status='succeeded' "
            "ORDER BY b.completedOn DESC, b.id DESC")

    def start(self, target: int, started) -> int:
        return self._db.insert('INSERT INTO Backup (modelElement, startedOn) VALUES (%s, %s)', (target, started))

    def is_running(self, target: int) -> bool:
        return bool(self._db.query("SELECT id FROM Backup WHERE modelElement=%s AND status='running' LIMIT 1", (target,)))

    def remove_database(self, target: int) -> None:
        self._db.execute('DELETE FROM DataManagerDataPackage WHERE dataPackage=%s', (target,))

    def delete(self, identity: int) -> None:
        self._db.execute("DELETE FROM Backup WHERE id=%s AND status='succeeded'", (identity,))

    def finish(self, identity: int, completed, *, result: dict | None = None, error: str | None = None) -> None:
        if result is not None:
            self._db.execute("UPDATE Backup SET status='succeeded', completedOn=%s, pathname=%s, "
                             "sizeBytes=%s, checksum=%s WHERE id=%s AND status='running'",
                             (completed, result['pathname'], result['sizeBytes'], result['checksum'], identity))
        else:
            self._db.execute("UPDATE Backup SET status='failed', completedOn=%s, error=%s "
                             "WHERE id=%s AND status='running'", (completed, error, identity))
