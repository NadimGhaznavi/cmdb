"""Explicit database deletion while retaining backup history."""

from threading import Event

from cmdb.activity.Scheduler import Scheduler
from cmdb.interface.BackupDb import BackupDb
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.SSH import SSH
from cmdb.interface.SSHDb import SSHDb


class DatabaseManager:
    def delete(self, identity, confirmation):
        db = DbMgr()
        try:
            backups = BackupDb(db)
            item = next((item for item in backups.databases() if item['modelElement'] == identity), None)
            if item is None:
                raise LookupError('User database not found.')
            name = item['databaseName']
            if name.lower() in ('cmdb', 'mysql', 'information_schema', 'performance_schema', 'sys'):
                raise ValueError('This database cannot be deleted.')
            if confirmation != name:
                raise ValueError('Confirm the exact database name.')
            if backups.is_running(identity):
                raise RuntimeError('A backup is running. Wait for it to finish before deleting the database.')
        finally:
            db.close()
        if item['scheduleId'] is not None:
            Scheduler().update(identity, False, item['expression'], item['retention'])
        SSHDb(SSH(), Event()).drop_db(item['ipAddress'], name)
        db = DbMgr()
        try:
            BackupDb(db).remove_database(identity)
        finally:
            db.close()
