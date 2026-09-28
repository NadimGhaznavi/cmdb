"""Deletion boundaries without touching a live database."""

import importlib.util
from pathlib import Path
from threading import Event
import unittest
from unittest.mock import Mock, patch

from cmdb.activity.DatabaseManager import DatabaseManager
from cmdb.interface.SSHDb import SSHDb


class DatabaseDeleteTests(unittest.TestCase):
    def test_host_helper_rejects_protected_names_and_quotes_identifiers(self):
        spec = importlib.util.spec_from_file_location('drop_database', Path('cmdb/interface/scripts/drop-database.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module.subprocess, 'run') as run:
            for name in ('cmdb', 'CMDB', 'mysql', 'sys', 'information_schema', 'performance_schema', ''):
                with patch('sys.argv', ['drop-database.py', name]), self.assertRaises(ValueError):
                    module.main()
            run.assert_not_called()
            with patch('sys.argv', ['drop-database.py', 'a`b']):
                module.main()
            self.assertEqual(run.call_args.kwargs['input'], 'DROP DATABASE IF EXISTS `a``b`;\n')
            self.assertIn('--binary-mode', run.call_args.args[0])

    def test_ssh_layer_never_contacts_host_for_cmdb(self):
        ssh = Mock()
        with self.assertRaises(ValueError):
            SSHDb(ssh, Event()).drop_db('192.0.2.1', 'CMDB')
        ssh.run.assert_not_called()
        ssh.is_local.assert_not_called()

    @patch('cmdb.activity.DatabaseManager.SSHDb')
    @patch('cmdb.activity.DatabaseManager.Scheduler')
    @patch('cmdb.activity.DatabaseManager.BackupDb')
    @patch('cmdb.activity.DatabaseManager.DbMgr')
    def test_confirmed_delete_disables_schedule_and_unlinks_inventory(self, db, records, scheduler, remote):
        item = dict(modelElement=7, databaseName='app', ipAddress='192.0.2.1', scheduleId=2,
                    expression='0 12 * * *', retention='forever')
        records.return_value.databases.return_value = [item]
        records.return_value.is_running.return_value = False
        DatabaseManager().delete(7, 'app')
        scheduler.return_value.update.assert_called_once_with(7, False, '0 12 * * *', 'forever')
        remote.return_value.drop_db.assert_called_once_with('192.0.2.1', 'app')
        records.return_value.remove_database.assert_called_once_with(7)
        records.return_value.remove_database.reset_mock()
        remote.return_value.drop_db.side_effect = OSError('denied')
        with self.assertRaises(OSError):
            DatabaseManager().delete(7, 'app')
        records.return_value.remove_database.assert_not_called()

    @patch('cmdb.activity.DatabaseManager.SSHDb')
    @patch('cmdb.activity.DatabaseManager.Scheduler')
    @patch('cmdb.activity.DatabaseManager.BackupDb')
    @patch('cmdb.activity.DatabaseManager.DbMgr')
    def test_protected_mismatch_and_running_backup_do_not_drop(self, db, records, scheduler, remote):
        for name, confirmation, running, error in [('cmdb', 'cmdb', False, ValueError),
                ('app', 'wrong', False, ValueError), ('app', 'app', True, RuntimeError)]:
            records.return_value.databases.return_value = [dict(modelElement=7, databaseName=name)]
            records.return_value.is_running.return_value = running
            with self.assertRaises(error):
                DatabaseManager().delete(7, confirmation)
        remote.assert_not_called()
        scheduler.assert_not_called()
