"""Policy edits and standalone dispatch without system cron or HTTP."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from cmdb.activity.Scheduler import Scheduler


class SchedulerTests(unittest.TestCase):
    def test_disabled_or_deleted_schedule_does_not_start_a_job(self):
        with patch('cmdb.activity.Scheduler.DbMgr') as db, \
                patch('cmdb.activity.Scheduler.BackupScheduleDb') as records, \
                patch('cmdb.activity.Scheduler.BackupManager') as manager:
            for schedule in (None, {'enabled': 0, 'modelElement': 4}):
                records.return_value.get.return_value = schedule
                self.assertTrue(Scheduler().run(12))
            manager.assert_not_called()
            self.assertEqual(db.return_value.close.call_count, 2)

    def test_runner_dispatches_enabled_schedule_and_returns_failure(self):
        with patch('cmdb.activity.Scheduler.DbMgr'), \
                patch('cmdb.activity.Scheduler.BackupScheduleDb') as records, \
                patch('cmdb.activity.Scheduler.BackupManager') as manager:
            records.return_value.get.return_value = {'enabled': 1, 'modelElement': 4}
            manager.return_value.execute.return_value = False
            self.assertFalse(Scheduler().run(12))
            manager.return_value.execute.assert_called_once_with(4)
            manager.return_value.stop.assert_called_once()

    def test_invalid_policy_never_touches_cron_or_database(self):
        with patch('cmdb.activity.Scheduler.DbMgr') as db, patch('cmdb.activity.Scheduler.Cron') as cron:
            for values in ((True, True, '0 12 * * *', 'forever'), (1, 1, '0 12 * * *', 'forever'),
                           (1, True, 'weekly', 'forever'), (1, True, '0 12 * * *', 'invalid')):
                with self.assertRaises(ValueError):
                    Scheduler().update(*values)
            db.assert_not_called()
            cron.assert_not_called()

    def test_cron_failure_rolls_back_policy(self):
        with patch('cmdb.activity.Scheduler.DbMgr') as db, \
                patch('cmdb.activity.Scheduler.BackupDb') as inventory, \
                patch('cmdb.activity.Scheduler.BackupScheduleDb') as records, \
                patch('cmdb.activity.Scheduler.Cron') as cron:
            inventory.return_value.databases.return_value = [{'modelElement': 4}]
            records.return_value.save.return_value = {'id': 12}
            cron.return_value.update.side_effect = OSError('Permission denied')
            with self.assertRaises(OSError):
                Scheduler().update(4, True, '0 12 * * *', 'forever')
            self.assertIs(db.return_value.transaction.return_value.__exit__.call_args.args[0], OSError)
            db.return_value.close.assert_called_once()

    def test_cli_loads_its_configuration_and_sets_exit_status(self):
        spec = importlib.util.spec_from_file_location('backup_runner', Path(__file__).resolve().parents[1] / 'cmdb-backup.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module.DatabaseEnvironment, 'read', return_value={'DB_NAME': 'test'}), \
                patch.object(module, 'Scheduler') as scheduler, \
                patch.object(module.os, 'environ', {}), patch('sys.argv', ['cmdb-backup.py', '--schedule-id', '12']):
            for success, code in ((True, 0), (False, 1)):
                scheduler.return_value.run.return_value = success
                self.assertEqual(module.main(), code)
                scheduler.return_value.run.assert_called_with(12)
                self.assertEqual(module.os.environ['DB_NAME'], 'test')
