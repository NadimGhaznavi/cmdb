"""Persistence for the single configured-network discovery policy."""

from cmdb.interface.DbMgr import DbMgr


class DiscoveryScheduleDb:
    def __init__(self, db: DbMgr) -> None:
        self._db = db

    def get(self, identity: int = 1) -> dict | None:
        rows = self._db.query('SELECT * FROM DiscoverySchedule WHERE id=%s', (identity,))
        return rows[0] if rows else None

    def save(self, enabled: bool, expression: str) -> dict:
        self._db.execute(
            'INSERT INTO DiscoverySchedule (id, enabled, expression) VALUES (1, %s, %s) '
            'ON DUPLICATE KEY UPDATE enabled=VALUES(enabled), expression=VALUES(expression)',
            (enabled, expression))
        return self.get()
