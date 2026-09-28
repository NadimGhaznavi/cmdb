"""Save backup policies, maintain cron entries, and dispatch one scheduled job."""

from cmdb.activity.BackupManager import BackupManager
from cmdb.interface.BackupDb import BackupDb
from cmdb.interface.BackupScheduleDb import BackupScheduleDb
from cmdb.interface.Cron import Cron
from cmdb.interface.DbMgr import DbMgr


class Scheduler:
    # Serialize web edits to the single service-account crontab.
    _edit_lock = Cron.EDIT_LOCK

    def update(self, modelElement: int, enabled: bool, frequency: str, retention: str) -> dict:
        if (type(modelElement) is not int or not 0 < modelElement < 2**64
                or type(enabled) is not bool or frequency != 'daily'
                or retention not in ('1-week', '2-weeks', '1-month', 'forever')):
            raise ValueError('Invalid backup schedule settings.')
        with self._edit_lock:
            db = DbMgr()
            try:
                with db.transaction():
                    if not any(item['modelElement'] == modelElement for item in BackupDb(db).databases()):
                        raise LookupError('User database not found.')
                    schedule = BackupScheduleDb(db).save(modelElement, enabled, frequency, retention)
                    Cron().update(schedule['id'], enabled)
                return schedule
            finally:
                db.close()

    def delete(self, identity: int) -> None:
        with self._edit_lock:
            db = DbMgr()
            try:
                with db.transaction():
                    Cron().delete(identity)
                    BackupScheduleDb(db).delete(identity)
            finally:
                db.close()

    def run(self, identity: int) -> bool:
        db = DbMgr()
        try:
            schedule = BackupScheduleDb(db).get(identity)
        finally:
            db.close()
        if schedule is None or not schedule['enabled']:
            return True
        manager = BackupManager()
        try:
            return manager.execute(schedule['modelElement'])
        finally:
            manager.stop()
