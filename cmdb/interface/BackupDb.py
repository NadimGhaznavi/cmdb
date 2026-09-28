"""Backup inventory lookup and attempt persistence."""

from cmdb.interface.DbMgr import DbMgr


class BackupDb:
    def __init__(self, db: DbMgr) -> None:
        self._db = db

    def databases(self) -> list[dict]:
        return self._db.query(
            "SELECT s.id AS modelElement, me.name AS databaseName, m.hostName, m.ipAddress, "
            "m.id AS machine, bs.id AS scheduleId, COALESCE(bs.enabled, 0) AS enabled, "
            "COALESCE(bs.frequency, 'daily') AS frequency, COALESCE(bs.retention, '1-week') AS retention, "
            "(SELECT MAX(b.completedOn) FROM Backup b WHERE b.modelElement=s.id "
            "AND b.status='succeeded') AS lastBackup, "
            "(SELECT b.id FROM Backup b WHERE b.modelElement=s.id ORDER BY b.id DESC LIMIT 1) AS latestBackup "
            "FROM `Schema` s JOIN ModelElement me ON me.id=s.id "
            "JOIN DataManager dm ON dm.id=me.namespace JOIN DeployedComponent dc ON dc.id=dm.id "
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

    def get(self, identity: int) -> dict | None:
        rows = self._db.query('SELECT * FROM Backup WHERE id=%s', (identity,))
        return rows[0] if rows else None

    def files(self) -> list[dict]:
        """Recorded successful database dumps, newest completion first."""
        return self._db.query(
            "SELECT b.id, b.completedOn AS backupTime, "
            "TIMESTAMPDIFF(SECOND, b.startedOn, b.completedOn) AS elapsedSeconds, me.name AS databaseName, "
            "m.hostName, m.ipAddress, b.pathname FROM Backup b "
            "JOIN `Schema` s ON s.id=b.modelElement JOIN ModelElement me ON me.id=s.id "
            "JOIN DataManager dm ON dm.id=me.namespace JOIN DeployedComponent dc ON dc.id=dm.id "
            "JOIN Machine m ON m.id=dc.machine WHERE b.status='succeeded' "
            "ORDER BY b.completedOn DESC, b.id DESC")

    def start(self, target: int, started) -> int:
        return self._db.insert('INSERT INTO Backup (modelElement, startedOn) VALUES (%s, %s)', (target, started))

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
