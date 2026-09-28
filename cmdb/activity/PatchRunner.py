"""Single independent worker for queued patches and post-reboot verification."""

from datetime import datetime, timedelta, timezone
import logging
import subprocess
import time
from uuid import UUID

from cmdb.interface.DbMgr import DbMgr
from cmdb.interface.PatchDb import PatchDb
from cmdb.interface.SSHPatch import SSHPatch


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PatchRunner:
    def record(self, method, *args):
        db = DbMgr()
        try:
            return getattr(PatchDb(db), method)(*args)
        finally:
            db.close()

    def execute(self, job):
        identity, address = job['id'], job['address']
        remote = SSHPatch()
        try:
            if job['status'] == 'patching':
                raise RuntimeError('Runner interrupted during patching. Inspect apt/dpkg before retrying.')
            if job['status'] == 'queued':
                job['bootId'] = str(UUID(remote.run(address, 'probe').strip()))
                self.record('start', identity, job['bootId'])
                output = remote.run(address, 'patch')
                self.record('rebooting', identity, output)
                job['rebootOn'] = now()
                remote.run(address, 'reboot')
            deadline = job['rebootOn'] + timedelta(minutes=15)
            while now() < deadline:
                try:
                    boot = str(UUID(remote.run(address, 'probe').strip()))
                except (OSError, ValueError, subprocess.SubprocessError):
                    time.sleep(5)
                    continue
                if boot != job['bootId']:
                    remote.run(address, 'verify')
                    self.record('finish', identity)
                    return
                time.sleep(5)
            raise TimeoutError('Host did not complete a verified reboot within 15 minutes.')
        except Exception as error:
            message = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
            logging.exception('Patch job %s failed', identity)
            self.record('finish', identity, message or type(error).__name__)

    def serve(self):
        while True:
            job = self.record('next')
            if job:
                self.execute(job)
            else:
                time.sleep(2)
