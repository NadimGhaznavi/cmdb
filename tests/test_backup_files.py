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
