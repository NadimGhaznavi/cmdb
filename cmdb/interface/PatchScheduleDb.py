"""Persist each machine's cron patch schedule."""


class PatchScheduleDb:
    def __init__(self, db):
        self.db = db

    def get(self, identity):
        rows = self.db.query('SELECT * FROM PatchSchedule WHERE id=%s', (identity,))
        return rows[0] if rows else None

    def save(self, machine, enabled, expression):
        self.db.execute('INSERT INTO PatchSchedule (machine, enabled, expression) VALUES (%s,%s,%s) '
                        'ON DUPLICATE KEY UPDATE enabled=VALUES(enabled), expression=VALUES(expression)',
                        (machine, enabled, expression))
        return self.db.query('SELECT * FROM PatchSchedule WHERE machine=%s', (machine,))[0]
