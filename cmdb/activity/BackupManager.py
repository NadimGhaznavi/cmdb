"""Execute requested backups and record outcomes; no scheduling."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import logging
import subprocess
from threading import Event, Lock
from urllib.parse import quote

from cmdb.interface.BackupDb import BackupDb
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.SSH import SSH
from cmdb.interface.SSHDb import SSHDb


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BackupManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._active = {}
        self._closed = False
        self._recovered = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='backup')

    def recover(self) -> None:
        with self._lock:
            if not self._recovered:
                db = DbMgr()
                try:
                    BackupDb(db).recover()
                    self._recovered = True
                finally:
                    db.close()

    def request_backup(self, target: int) -> int:
        with self._lock:
            if self._closed:
                raise RuntimeError('Backup manager is stopping.')
            if target in self._active:
                return self._active[target]
            db = DbMgr()
            try:
                inventory = BackupDb(db)
                if not self._recovered:
                    inventory.recover()
                    self._recovered = True
                item = next((row for row in inventory.databases() if row['modelElement'] == target), None)
                if item is None:
                    raise LookupError('User database not found.')
                started = now()
                identity = inventory.start(target, started)
            finally:
                db.close()
            self._active[target] = identity
            self._executor.submit(self._run, item, identity, started)
            return identity

    def _run(self, item: dict, identity: int, started) -> None:
        result = None
        error = None
        try:
            host = quote((item['hostName'] or item['ipAddress']).split('.')[0]
                         if item['hostName'] else item['ipAddress'], safe='-_.')
            name = quote(item['databaseName'], safe='-_.')[:80]
            filename = f"mariadb-{host[:63]}-{name}-{started:%Y-%m-%d_%H:%M:%S}.dump"
            pathname = f'{host}/db/{filename}'
            result = SSHDb(SSH(), Event()).backup_db(item['ipAddress'], item['databaseName'], pathname)
        except subprocess.CalledProcessError as failure:
            error = (failure.stderr or f'Backup command exited with status {failure.returncode}.')[-4000:]
        except subprocess.TimeoutExpired:
            error = 'Backup command timed out; file outcome may be unknown.'
        except Exception as failure:
            logging.exception('Backup %s failed', identity)
            error = str(failure)[:4000] or type(failure).__name__
        try:
            db = DbMgr()
            try:
                BackupDb(db).finish(identity, max(now(), started), result=result, error=error)
            finally:
                db.close()
        except Exception:
            logging.exception('Could not record completion of backup %s', identity)
            # Keep the target blocked until restart rather than permit an uncertain retry.
            return
        with self._lock:
            self._active.pop(item['modelElement'], None)

    def stop(self) -> None:
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=True)
