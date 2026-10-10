"""Execute requested backups and record outcomes; no scheduling."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import PurePosixPath
import logging
import subprocess
from threading import Event, Lock
from urllib.parse import quote

from cmdb.interface.BackupDb import BackupDb
from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.SSH import SSH
from cmdb.interface.SSHDb import SSHDb
from cmdb.interface.SSHFiles import SSHFiles


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BackupManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._active = {}
        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='backup')

    def _prepare(self, target: int):
        db = DbMgr()
        try:
            inventory = BackupDb(db)
            item = inventory.target(target)
            if item is None:
                raise LookupError('Backup target not found.')
            started = now()
            return item, inventory.start(target, started), started
        finally:
            db.close()

    def execute(self, target: int) -> bool:
        """Run one complete job in the calling process, including bookkeeping."""
        return self._run(*self._prepare(target))

    def request_backup(self, target: int) -> int:
        with self._lock:
            if self._closed:
                raise RuntimeError('Backup manager is stopping.')
            if target in self._active:
                return self._active[target]
            item, identity, started = self._prepare(target)
            self._active[target] = identity
            self._executor.submit(self._run, item, identity, started)
            return identity

    def _run(self, item: dict, identity: int, started) -> bool:
        result = None
        error = None
        try:
            host = quote((item['hostName'] or item['ipAddress']).split('.')[0]
                         if item['hostName'] else item['ipAddress'], safe='-_.')
            if item.get('kind') == 'directory':
                application = quote(item['applicationName'].lower(), safe='-_.')
                name = quote(PurePosixPath(item['pathname']).name, safe='-_.')
                filename = f"{host[:63]}-{application[:80]}-{name[:80]}-{started:%Y-%m-%d_%H:%M:%S}.tgz"
                pathname = f'{host}/files/{filename}'
                result = SSHFiles(SSH()).backup_directory(item['ipAddress'], item['pathname'], pathname)
            else:
                name = quote(item['databaseName'], safe='-_.')
                filename = f"mariadb-{host[:63]}-{name[:80]}-{started:%Y-%m-%d_%H:%M:%S}.dump"
                pathname = f'{host}/db/{name}/{filename}'
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
            return False
        with self._lock:
            self._active.pop(item['modelElement'], None)
        if error:
            logging.error('Backup %s failed: %s', identity, error)
        return error is None

    def stop(self) -> None:
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=True)
