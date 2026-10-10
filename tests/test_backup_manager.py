"""On-demand coordination without remote commands or production database access."""

from datetime import datetime
import subprocess
from threading import Event
import unittest
from unittest.mock import Mock, patch

from cmdb.activity.BackupManager import BackupManager


class BackupManagerTests(unittest.TestCase):
    def test_directory_backup_uses_host_files_path_and_records_metadata(self):
        item = dict(modelElement=12, hostName='wintermute.example', ipAddress='192.0.2.2',
                    kind='directory', applicationName='MyCount', componentName='Marketing Screenshots',
                    pathname='/opt/prod/mycount/pages/marketing')
        metadata = dict(pathname='wintermute/files/wintermute-mycount-marketing-2026-10-07_15:53:01.tgz',
                        sizeBytes=42, checksum='a' * 64)
        with patch('cmdb.activity.BackupManager.DbMgr'), \
                patch('cmdb.activity.BackupManager.BackupDb') as records, \
                patch('cmdb.activity.BackupManager.SSHFiles') as remote, \
                patch('cmdb.activity.BackupManager.SSHDb') as database:
            remote.return_value.backup_directory.return_value = metadata
            manager = BackupManager()
            try:
                self.assertTrue(manager._run(item, 23, datetime(2026, 10, 7, 15, 53, 1)))
            finally:
                manager.stop()
            remote.return_value.backup_directory.assert_called_once_with(
                '192.0.2.2', item['pathname'], metadata['pathname'])
            database.assert_not_called()
            self.assertEqual(records.return_value.finish.call_args.kwargs, {'result': metadata, 'error': None})

    def test_duplicate_requests_share_attempt_and_persist_remote_result(self):
        started, release = Event(), Event()
        item = dict(modelElement=12, hostName='sally.example', ipAddress='192.0.2.2', databaseName='cmdb')
        metadata = dict(pathname='sally/db/cmdb/file.dump', sizeBytes=42, checksum='a' * 64)
        def dump(*args):
            started.set()
            self.assertTrue(release.wait(5))
            self.assertEqual(args[:2], ('192.0.2.2', 'cmdb'))
            self.assertTrue(args[2].startswith('sally/db/cmdb/mariadb-sally-cmdb-'))
            return metadata
        with patch('cmdb.activity.BackupManager.DbMgr') as db, \
                patch('cmdb.activity.BackupManager.BackupDb') as records, \
                patch('cmdb.activity.BackupManager.SSHDb') as remote:
            records.return_value.target.return_value = item
            records.return_value.start.return_value = 23
            remote.return_value.backup_db.side_effect = dump
            manager = BackupManager()
            try:
                self.assertEqual(manager.request_backup(12), 23)
                self.assertTrue(started.wait(3))
                self.assertEqual(manager.request_backup(12), 23)
                records.return_value.start.assert_called_once()
            finally:
                release.set()
                manager.stop()
            remote.return_value.backup_db.assert_called_once()
            self.assertEqual(records.return_value.finish.call_args.kwargs, {'result': metadata, 'error': None})
            self.assertEqual(db.return_value.close.call_count, 2)

    def test_failure_is_recorded_and_missing_target_never_runs(self):
        with patch('cmdb.activity.BackupManager.DbMgr'), \
                patch('cmdb.activity.BackupManager.BackupDb') as records, \
                patch('cmdb.activity.BackupManager.SSHDb') as remote:
            records.return_value.target.return_value = None
            manager = BackupManager()
            try:
                with self.assertRaises(LookupError):
                    manager.request_backup(999)
                records.return_value.start.assert_not_called()
                remote.return_value.backup_db.assert_not_called()
                remote.return_value.backup_db.side_effect = subprocess.CalledProcessError(1, 'dump', stderr='Permission denied')
                manager._run(dict(modelElement=1, hostName=None, ipAddress='192.0.2.1', databaseName='db'), 2, datetime.now())
                self.assertEqual(records.return_value.finish.call_args.kwargs,
                                 {'result': None, 'error': 'Permission denied'})
            finally:
                manager.stop()
