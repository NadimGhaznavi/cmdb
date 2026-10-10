"""Manage CMDB backup, patch, and discovery entries in the service account's crontab."""

import re
import shlex
from threading import Lock

from crontab import CronTab

from cmdb.constants.DCMDB import DCMDB


class Cron:
    PREFIX = 'cmdb-backup-schedule-'
    PATCH_PREFIX = 'cmdb-patch-schedule-'
    DISCOVERY_PREFIX = 'cmdb-discovery-schedule-'
    EDIT_LOCK = Lock()

    def __init__(self, user=True) -> None:
        self._user = user

    def update(self, schedule: int, enabled: bool, expression: str = DCMDB.BACKUP_CRON) -> None:
        self._update(schedule, enabled, self.PREFIX, 'cmdb-backup.py', expression)

    def update_patch(self, schedule: int, enabled: bool, expression: str) -> None:
        self._update(schedule, enabled, self.PATCH_PREFIX, 'cmdb-patch.py', expression)

    def update_discovery(self, schedule: int, enabled: bool, expression: str) -> None:
        self._update(schedule, enabled, self.DISCOVERY_PREFIX, 'cmdb-discovery.py', expression)

    def _update(self, schedule, enabled, prefix, runner, expression):
        if type(schedule) is not int or schedule <= 0:
            raise ValueError('Invalid schedule ID.')
        tab = CronTab(user=self._user)
        comment = prefix + str(schedule)
        tab.remove_all(comment=comment)
        if enabled:
            command = shlex.join([DCMDB.BASE_DIR + '/.venv/bin/python', '-B',
                                  DCMDB.BASE_DIR + '/' + runner, '--schedule-id', str(schedule)])
            job = tab.new(command=command.replace('%', r'\%'), comment=comment)
            job.setall(expression)
        tab.write()

    def delete(self, schedule: int) -> None:
        self.update(schedule, False)

    def clear(self) -> None:
        """Used by uninstall; unrelated jobs are preserved."""
        tab = CronTab(user=self._user)
        tab.remove_all(comment=re.compile(r'^' + self.PREFIX + r'[0-9]+$'))
        tab.remove_all(comment=re.compile(r'^' + self.PATCH_PREFIX + r'[0-9]+$'))
        tab.remove_all(comment=re.compile(r'^' + self.DISCOVERY_PREFIX + r'[0-9]+$'))
        tab.write()
