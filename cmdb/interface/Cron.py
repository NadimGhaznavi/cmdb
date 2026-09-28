"""Manage only CMDB backup entries in the service account's crontab."""

import re
import shlex

from crontab import CronTab

from cmdb.constants.DCmdb import DCmdb


class Cron:
    PREFIX = 'cmdb-backup-schedule-'

    def __init__(self, user=True) -> None:
        self._user = user

    def update(self, schedule: int, enabled: bool) -> None:
        if type(schedule) is not int or schedule <= 0:
            raise ValueError('Invalid schedule ID.')
        tab = CronTab(user=self._user)
        comment = self.PREFIX + str(schedule)
        tab.remove_all(comment=comment)
        if enabled:
            command = shlex.join([DCmdb.BASE_DIR + '/.venv/bin/python', '-B',
                                  DCmdb.BASE_DIR + '/cmdb-backup.py', '--schedule-id', str(schedule)])
            job = tab.new(command=command.replace('%', r'\%'), comment=comment)
            job.setall(DCmdb.BACKUP_CRON)
        tab.write()

    def delete(self, schedule: int) -> None:
        self.update(schedule, False)

    def clear(self) -> None:
        """Used by uninstall; unrelated jobs are preserved."""
        tab = CronTab(user=self._user)
        tab.remove_all(comment=re.compile(r'^' + self.PREFIX + r'[0-9]+$'))
        tab.write()
