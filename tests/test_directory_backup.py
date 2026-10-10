"""Real archive contents and host command validation without production access."""

import hashlib
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cmdb.interface.SSHFiles import SSHFiles


SCRIPT = Path(__file__).resolve().parents[1] / 'cmdb/interface/scripts/backup-files.sh'


class DirectoryBackupTests(unittest.TestCase):
    def test_archive_contents_metadata_and_no_overwrite_or_partial_output(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'app data' / 'marketing'
            source.mkdir(parents=True)
            (source / 'screenshot.txt').write_text('marketing content')
            (source / 'nested').mkdir()
            (source / 'nested' / 'file.txt').write_text('nested content')
            (source / 'link').symlink_to('screenshot.txt')
            destination = root / 'backups'
            destination.mkdir()
            relative = 'host/files/host-mycount-marketing-2026-10-07_15:53:01.tgz'
            command = ['sh', str(SCRIPT), str(destination), relative, str(source)]
            result = subprocess.run(command, text=True, capture_output=True, check=True)
            archive = destination / relative
            original = archive.read_bytes()
            self.assertEqual(result.stdout.split(), [str(len(original)), hashlib.sha256(original).hexdigest()])
            self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
            with tarfile.open(archive, 'r:gz') as contents:
                self.assertEqual(contents.extractfile('marketing/screenshot.txt').read(), b'marketing content')
                self.assertEqual(contents.extractfile('marketing/nested/file.txt').read(), b'nested content')
                self.assertTrue(contents.getmember('marketing/link').issym())
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(archive.read_bytes(), original)
            command[3] = 'host/files/failed.tgz'
            command[4] = str(root / 'missing')
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertFalse((destination / command[3]).exists())
            command[4] = str(root)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertFalse((destination / command[3]).exists())
            self.assertEqual(list(archive.parent.glob('.backup-*')), [])

    @patch('cmdb.interface.SSHFiles.SSH')
    def test_ssh_archives_directory_and_rejects_unsafe_inputs(self, ssh):
        ssh.return_value.run.return_value.stdout = '42 ' + 'a' * 64
        relative = 'host/files/host-mycount-marketing-2026-10-07_15:53:01.tgz'
        result = SSHFiles(ssh()).backup_directory('192.0.2.1', '/app/marketing', relative)
        self.assertEqual(result, dict(pathname=relative, sizeBytes=42, checksum='a' * 64))
        call = ssh.return_value.run.call_args
        self.assertEqual(call.args[0], '192.0.2.1')
        self.assertIn('/app/marketing', call.args[1])
        for source, destination in [('/', relative), ('relative/path', relative),
                                    ('/app/../etc', relative), ('/app', '../host/files/file.tgz'),
                                    ('/app', '/host/files/file.tgz'), ('/app', 'host/db/file.tgz')]:
            with self.assertRaises(ValueError):
                SSHFiles(ssh()).backup_directory('192.0.2.1', source, destination)
        ssh.return_value.run.assert_called_once()
        ssh.return_value.run.return_value.stdout = 'invalid'
        with self.assertRaises(ValueError):
            SSHFiles(ssh()).backup_directory('192.0.2.1', '/app/marketing', relative)
