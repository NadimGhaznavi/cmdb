"""Discovery policy validation, cron isolation, and independent execution."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from crontab import CronTab

from cmdb.activity.DiscoveryScheduler import DiscoveryScheduler
from cmdb.interface.Cron import Cron


class DiscoverySchedulerTests(unittest.TestCase):
    def test_cron_update_disable_and_cleanup_preserve_other_jobs(self):
        tab = CronTab(tab='0 12 * * * /backup # cmdb-backup-schedule-1\n'
                          '15 2 * * * /patch # cmdb-patch-schedule-1\n'
                          '0 0 * * * /other # unrelated\n'
                          '0 0 * * * /custom # cmdb-discovery-schedule-custom\n')
        with patch('cmdb.interface.Cron.CronTab', return_value=tab):
            Cron().update_discovery(1, True, '*/5 * * * *')
            Cron().update_discovery(1, True, '15 3 * * 0')
            jobs = list(tab.find_comment('cmdb-discovery-schedule-1'))
            self.assertEqual(len(jobs), 1)
            self.assertEqual(str(jobs[0].slices), '15 3 * * 0')
            self.assertIn('/cmdb-discovery.py --schedule-id 1', jobs[0].command)
            Cron().update_discovery(1, False, '15 3 * * 0')
            self.assertEqual(len(tab), 4)
            Cron().update_discovery(1, True, '*/5 * * * *')
            Cron().clear()
        self.assertEqual([job.command for job in tab], ['/other', '/custom'])

    def test_invalid_settings_never_touch_database_or_cron(self):
        with patch('cmdb.activity.DiscoveryScheduler.DbMgr') as db, \
                patch('cmdb.activity.DiscoveryScheduler.Cron') as cron:
            for enabled, expression in ((1, '* * * * *'), (True, '@daily'),
                                        (True, '99 * * * *'), (False, ''),
                                        (True, '* * * * *\n'), (True, None)):
                with self.assertRaises(ValueError):
                    DiscoveryScheduler().update(enabled, expression)
            db.assert_not_called()
            cron.assert_not_called()

    def test_cron_failure_rolls_back_and_closes_connection(self):
        with patch('cmdb.activity.DiscoveryScheduler.DbMgr') as db, \
                patch('cmdb.activity.DiscoveryScheduler.DiscoveryScheduleDb') as records, \
                patch('cmdb.activity.DiscoveryScheduler.Cron') as cron:
            records.return_value.save.return_value = {'id': 1}
            cron.return_value.update_discovery.side_effect = OSError('Permission denied')
            with self.assertRaises(OSError):
                DiscoveryScheduler().update(True, ' */5  * * * * ')
            records.return_value.save.assert_called_once_with(True, '*/5 * * * *')
            self.assertIs(db.return_value.transaction.return_value.__exit__.call_args.args[0], OSError)
            db.return_value.close.assert_called_once()

    def test_deleted_or_disabled_policy_never_scans(self):
        with patch('cmdb.activity.DiscoveryScheduler.DbMgr'), \
                patch('cmdb.activity.DiscoveryScheduler.DiscoveryScheduleDb') as records, \
                patch('cmdb.activity.DiscoveryScheduler.InventoryCoordinator') as worker:
            for policy in (None, {'enabled': 0}):
                records.return_value.get.return_value = policy
                self.assertTrue(DiscoveryScheduler().run(1))
            worker.assert_not_called()

    def test_enabled_policy_scans_and_prunes_even_on_failure(self):
        with patch('cmdb.activity.DiscoveryScheduler.DbMgr') as db, \
                patch('cmdb.activity.DiscoveryScheduler.DiscoveryScheduleDb') as records, \
                patch('cmdb.activity.DiscoveryScheduler.InventoryCoordinator') as worker:
            records.return_value.get.return_value = {'enabled': 1}
            worker.return_value.scan_inventory.side_effect = lambda: db.return_value.close.assert_called_once()
            self.assertTrue(DiscoveryScheduler().run(1))
            worker.return_value.start.assert_not_called()
            worker.return_value.prune.assert_called_once_with()
            worker.return_value.scan_inventory.side_effect = OSError('Scan failed')
            with self.assertRaises(OSError):
                DiscoveryScheduler().run(1)
            self.assertEqual(worker.return_value.prune.call_count, 2)

    def test_cli_loads_configuration_and_returns_failure(self):
        spec = importlib.util.spec_from_file_location('discovery_cli', Path('cmdb-discovery.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module.DatabaseEnvironment, 'read', return_value={'DB_NAME': 'test'}), \
                patch.object(module, 'DiscoveryScheduler') as scheduler, \
                patch.object(module.os, 'environ', {}), \
                patch('sys.argv', ['cmdb-discovery.py', '--schedule-id', '1']):
            self.assertEqual(module.main(), 0)
            self.assertEqual(module.os.environ['DB_NAME'], 'test')
            scheduler.return_value.run.assert_called_once_with(1)
            scheduler.return_value.run.side_effect = OSError('failure')
            with self.assertLogs(level='ERROR'):
                self.assertEqual(module.main(), 1)
