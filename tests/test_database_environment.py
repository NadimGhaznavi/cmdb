"""Credential files are parsed as data and validated at the boundary."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from cmdb.interface.DatabaseEnvironment import DatabaseEnvironment


class DatabaseEnvironmentTests(unittest.TestCase):
    def test_read_and_invalid_files(self):
        values = {'DB_HOST': 'localhost', 'DB_PORT': '3306', 'DB_NAME': 'cmdb',
                  'DB_USER': 'cmdb', 'DB_PASSWORD': '$(do-not-execute)'}
        text = ''.join(f'{key}={value}\n' for key, value in values.items())
        with TemporaryDirectory() as directory:
            path = Path(directory, 'database.env')
            path.write_text(text)
            self.assertEqual(DatabaseEnvironment.read(path), values)
            for invalid in (text + 'DB_NAME=other\n', text + 'EXTRA=1\n',
                            text.replace('DB_HOST=localhost\n', ''),
                            text.replace('3306', '0'), text.replace('3306', 'invalid'),
                            text.replace('DB_HOST=localhost', 'DB_HOST=')):
                with self.subTest(value=invalid):
                    path.write_text(invalid)
                    with self.assertRaises(ValueError):
                        DatabaseEnvironment.read(path)
