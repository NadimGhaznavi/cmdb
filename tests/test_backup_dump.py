"""Exercise host-side temporary files, publication, and failures with command fixtures."""

import hashlib
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'cmdb/interface/scripts/backup-db.sh'


class BackupDumpTests(unittest.TestCase):
    def test_dump_uses_destination_filesystem_and_never_publishes_partial_output(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / 'bin'
            binaries.mkdir()
            for name, contents in {
                'findmnt': '#!/bin/sh\nprintf "nfs4\\n"\n',
                'mariadb-dump': '#!/bin/sh\nprintf "database dump\\n"\nexit "${DUMP_EXIT:-0}"\n',
            }.items():
                executable = binaries / name
                executable.write_text(contents)
                executable.chmod(0o755)
            env = dict(os.environ, PATH=str(binaries) + ':' + os.environ['PATH'])
            command = ['sh', str(SCRIPT), str(root), 'host/db/test.dump', 'db', 'agent']
            result = subprocess.run(command, env=env, text=True, capture_output=True, check=True)
            final = root / 'host/db/test.dump'
            self.assertEqual(result.stdout.split(), [str(final.stat().st_size), hashlib.sha256(final.read_bytes()).hexdigest()])
            self.assertEqual(final.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(final.parent.glob('*.part')), [])
            self.assertEqual(list(final.parent.glob('.backup-*')), [])
            self.assertNotEqual(subprocess.run(command, env=env, capture_output=True).returncode, 0)
            self.assertEqual(final.read_text(), 'database dump\n')
            command[3] = 'host/db/failed.dump'
            self.assertNotEqual(subprocess.run(command, env=dict(env, DUMP_EXIT='1'), capture_output=True).returncode, 0)
            self.assertFalse((final.parent / 'failed.dump').exists())
            self.assertEqual(list(final.parent.glob('.backup-*')), [])
            (binaries / 'findmnt').write_text('#!/bin/sh\nprintf "ext4\\n"\n')
            rejected = subprocess.run(command, env=env, text=True, capture_output=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn('not mounted as NFS', rejected.stderr)
