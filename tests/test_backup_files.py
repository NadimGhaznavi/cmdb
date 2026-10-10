"""Filesystem metadata checks without production paths or account switching."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cmdb.interface.BackupFiles import BackupFiles


SCRIPT = Path(__file__).resolve().parents[1] / 'cmdb/interface/scripts/scan-backups.py'


class BackupFilesTests(unittest.TestCase):
    def test_delete_removes_only_recorded_file_and_accepts_missing_file(self):
        script = SCRIPT.with_name('delete-backup.py')
        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            base = Path(directory)
            dump = base / 'host/db/db/file.dump'
            dump.parent.mkdir(parents=True)
            dump.write_text('backup')
            other = dump.with_name('other.dump')
            other.write_text('keep')
            def delete(pathname):
                return subprocess.run([sys.executable, '-B', str(script)],
                                      input=json.dumps(dict(directory=directory, pathname=pathname)),
                                      text=True, capture_output=True, check=True)
            delete('host/db/db/file.dump')
            self.assertFalse(dump.exists())
            self.assertEqual(other.read_text(), 'keep')
            delete('host/db/db/file.dump')
            external = Path(outside) / 'external.dump'
            external.write_text('keep')
            (base / 'escape').symlink_to(outside, target_is_directory=True)
            (base / 'link.dump').symlink_to(other)
            for pathname in ('../external.dump', str(external), 'escape/external.dump',
                             'host/db/db', 'link.dump', '.'):
                with self.assertRaises(subprocess.CalledProcessError):
                    delete(pathname)
            self.assertEqual(external.read_text(), 'keep')
            self.assertEqual(other.read_text(), 'keep')

    @patch('cmdb.interface.BackupFiles.SSH')
    def test_delete_uses_local_agent_and_validates_path(self, ssh):
        BackupFiles().delete({'pathname': 'host/db/db/file.dump'})
        call = ssh.return_value.run.call_args
        self.assertEqual(call.args[0], '127.0.0.1')
        self.assertEqual(json.loads(call.kwargs['input'])['pathname'], 'host/db/db/file.dump')
        for pathname in ('/etc/passwd', '../file.dump', ''):
            with self.assertRaises(ValueError):
                BackupFiles().delete({'pathname': pathname})
        ssh.return_value.run.assert_called_once()

    def test_scan_finds_files_and_manual_deletions_without_reading_contents(self):
        with TemporaryDirectory() as directory:
            dump = Path(directory) / 'host/db/db/file.dump'
            dump.parent.mkdir(parents=True)
            dump.touch(mode=0o000)
            request = dict(directory=directory, paths=['host/db/db/file.dump', 'gone/db/db/file.dump'])
            def scan():
                return subprocess.run([sys.executable, '-B', str(SCRIPT)], input=json.dumps(request),
                                      text=True, capture_output=True, check=True)
            self.assertEqual(json.loads(scan().stdout), ['Found', 'Missing'])
            dump.unlink()
            self.assertEqual(json.loads(scan().stdout), ['Missing', 'Missing'])
            request['directory'] = directory + '/unavailable'
            with self.assertRaises(subprocess.CalledProcessError):
                scan()

    @patch('cmdb.interface.BackupFiles.SSH')
    def test_checks_as_local_agent_and_rejects_escaping_paths(self, ssh):
        ssh.return_value.run.return_value.stdout = '["Found"]'
        self.assertEqual(BackupFiles().scan([{'pathname': 'host/db/db/file.dump'}]), ['Found'])
        self.assertEqual(ssh.return_value.run.call_args.args[0], '127.0.0.1')
        for pathname in ('/etc/passwd', '../file.dump'):
            with self.assertRaises(ValueError):
                BackupFiles().scan([{'pathname': pathname}])
        ssh.return_value.run.assert_called_once()
