"""Persist separate kernel and other cron patch schedules for each machine."""


class PatchScheduleDb:
    def __init__(self, db):
        self.db = db

    def get(self, identity):
        rows = self.db.query('SELECT * FROM PatchSchedule WHERE id=%s', (identity,))
        return rows[0] if rows else None

    def save(self, machine, patchType, enabled, expression):
        self.db.execute('INSERT INTO PatchSchedule (machine, patchType, enabled, expression) VALUES (%s,%s,%s,%s) '
                        'ON DUPLICATE KEY UPDATE enabled=VALUES(enabled), expression=VALUES(expression)',
                        (machine, patchType, enabled, expression))
        return self.db.query('SELECT * FROM PatchSchedule WHERE machine=%s AND patchType=%s',
                             (machine, patchType))[0]
