"""Cron edits against an in-memory python-crontab, never the host crontab."""

import unittest
from unittest.mock import patch

from crontab import CronTab

from cmdb.constants.DCmdb import DCmdb
from cmdb.interface.Cron import Cron


class CronTests(unittest.TestCase):
    def test_create_update_disable_delete_preserve_unrelated_entries(self):
        tab = CronTab(tab='15 4 * * * /bin/true # unrelated\n')
        with patch('cmdb.interface.Cron.CronTab', return_value=tab):
            interface = Cron()
            interface.update(12, True)
            interface.update(12, True)
            jobs = list(tab.find_comment('cmdb-backup-schedule-12'))
            self.assertEqual(len(jobs), 1)
            self.assertEqual(str(jobs[0].slices), '0 12 * * *')
            self.assertEqual(jobs[0].command,
                             DCmdb.BASE_DIR + '/.venv/bin/python -B ' + DCmdb.BASE_DIR + '/cmdb-backup.py --schedule-id 12')
            interface.update(13, True)
            interface.delete(12)
            self.assertEqual(len(list(tab.find_comment('cmdb-backup-schedule-12'))), 0)
            self.assertEqual(len(list(tab.find_comment('cmdb-backup-schedule-13'))), 1)
            interface.update(13, False)
            self.assertEqual(len(tab), 1)
            self.assertIn('/bin/true', str(tab))

    def test_cleanup_uses_only_exact_cmdb_markers(self):
        tab = CronTab(tab='0 12 * * * /bin/a # cmdb-backup-schedule-1\n'
                          '0 12 * * * /bin/b # cmdb-backup-schedule-not-ours\n'
                          '0 12 * * * /bin/c # unrelated\n')
        with patch('cmdb.interface.Cron.CronTab', return_value=tab):
            Cron().clear()
        self.assertEqual([job.command for job in tab], ['/bin/b', '/bin/c'])

    def test_write_failure_is_reported(self):
        tab = CronTab(tab='')
        with patch('cmdb.interface.Cron.CronTab', return_value=tab), \
                patch.object(tab, 'write', side_effect=OSError('Permission denied')):
            with self.assertRaises(OSError):
                Cron().update(1, True)
