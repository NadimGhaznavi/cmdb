"""Persistence for application backup policies."""

from cmdb.interface.DbMgr import DbMgr


class BackupScheduleDb:
    def __init__(self, db: DbMgr) -> None:
        self._db = db

    def get(self, identity: int) -> dict | None:
        rows = self._db.query('SELECT * FROM BackupSchedule WHERE id=%s', (identity,))
        return rows[0] if rows else None

    def save(self, modelElement: int, enabled: bool, expression: str, retention: str) -> dict:
        self._db.execute(
            'INSERT INTO BackupSchedule (modelElement, enabled, expression, retention) VALUES (%s, %s, %s, %s) '
            'ON DUPLICATE KEY UPDATE enabled=VALUES(enabled), expression=VALUES(expression), retention=VALUES(retention)',
            (modelElement, enabled, expression, retention))
        return self._db.query('SELECT * FROM BackupSchedule WHERE modelElement=%s', (modelElement,))[0]

    def delete(self, identity: int) -> None:
        self._db.execute('DELETE FROM BackupSchedule WHERE id=%s', (identity,))
