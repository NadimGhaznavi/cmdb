"""Patch scheduling without writing live cron or queuing production jobs."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from crontab import CronTab
from cmdb.activity.PatchScheduler import PatchScheduler
from cmdb.interface.Cron import Cron


class PatchSchedulerTests(unittest.TestCase):
    def test_cron_markers_preserve_backup_and_unrelated_jobs(self):
        tab = CronTab(tab='0 12 * * * /backup # cmdb-backup-schedule-1\n15 2 * * * /other # unrelated\n')
        with patch('cmdb.interface.Cron.CronTab', return_value=tab):
            cron = Cron()
            cron.update_patch(1, True, '15 3 * * 0')
            cron.update_patch(1, True, '30 4 * * 1-5')
            jobs = list(tab.find_comment('cmdb-patch-schedule-1'))
            self.assertEqual(len(jobs), 1)
            self.assertIn('/cmdb-patch.py --schedule-id 1', jobs[0].command)
            self.assertEqual(str(jobs[0].slices), '30 4 * * 1-5')
            self.assertEqual(len(list(tab.find_comment('cmdb-backup-schedule-1'))), 1)
            cron.update_patch(1, False, '')
            self.assertEqual(len(tab), 2)
            cron.update_patch(2, True, '0 12 * * *')
            cron.clear()
            self.assertEqual([job.command for job in tab], ['/other'])

    def test_bad_cron_is_rejected_before_writes(self):
        with patch('cmdb.activity.PatchScheduler.DbMgr') as db:
            for expression in ('', '@reboot', '* * * *', '61 * * * *', '0 12 * * 0\n', '* * * * * /bin/reboot'):
                with self.subTest(expression=expression), self.assertRaises(ValueError):
                    PatchScheduler().update(1, True, expression)
            db.assert_not_called()

    def test_cron_failure_rolls_back_and_valid_expression_is_passed_through(self):
        with patch('cmdb.activity.PatchScheduler.DbMgr') as db, \
                patch('cmdb.activity.PatchScheduler.SoftwareDeploymentDb') as inventory, \
                patch('cmdb.activity.PatchScheduler.PatchScheduleDb') as records, \
                patch('cmdb.activity.PatchScheduler.Cron') as cron:
            inventory.return_value.debian_hosts.return_value = [{'id': 7}]
            records.return_value.save.return_value = {'id': 2}
            expression = '*/15 1-3 * * MON,FRI'
            PatchScheduler().update(7, True, expression)
            cron.return_value.update_patch.assert_called_with(2, True, expression)
            cron.return_value.update_patch.side_effect = OSError('denied')
            with self.assertRaises(OSError):
                PatchScheduler().update(7, True, expression)
            self.assertIs(db.return_value.transaction.return_value.__exit__.call_args.args[0], OSError)

    def test_cron_dispatch_rechecks_enabled_and_queues_without_web(self):
        with patch('cmdb.activity.PatchScheduler.DbMgr'), \
                patch('cmdb.activity.PatchScheduler.PatchScheduleDb') as schedules, \
                patch('cmdb.activity.PatchScheduler.PatchDb') as jobs:
            for record in (None, {'enabled': 0, 'machine': 7}):
                schedules.return_value.get.return_value = record
                PatchScheduler().run(2)
            jobs.return_value.request.assert_not_called()
            schedules.return_value.get.return_value = {'enabled': 1, 'machine': 7}
            PatchScheduler().run(2)
            jobs.return_value.request.assert_called_once_with(7)

    def test_cli_schedule_mode_does_not_start_worker(self):
        spec = importlib.util.spec_from_file_location('patch_cli', Path('cmdb-patch.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module.DatabaseEnvironment, 'read', return_value={}), \
                patch.object(module, 'PatchScheduler') as scheduler, patch.object(module, 'PatchRunner') as worker, \
                patch('sys.argv', ['cmdb-patch.py', '--schedule-id', '2']):
            self.assertEqual(module.main(), 0)
            scheduler.return_value.run.assert_called_once_with(2)
            worker.assert_not_called()
