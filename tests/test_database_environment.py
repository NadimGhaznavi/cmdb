"""Credential files are parsed as data and validated at the boundary."""

from pathlib import Path
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cmdb.interface.Database import connect_database
from cmdb.interface.DatabaseEnvironment import DatabaseEnvironment


class DatabaseEnvironmentTests(unittest.TestCase):
    def test_connection_resolves_environment_before_opening_manager(self):
        values = {'DB_HOST': 'database.example', 'DB_PORT': '3307', 'DB_NAME': 'inventory',
                  'DB_USER': 'reader', 'DB_PASSWORD': '$(do-not-execute)'}
        with patch.dict(os.environ, values, clear=True), patch('cmdb.interface.Database.DbMgr') as manager:
            self.assertIs(connect_database(), manager.return_value)
            self.assertEqual(manager.call_args.kwargs, {
                'host': 'database.example', 'port': 3307, 'database': 'inventory',
                'user': 'reader', 'password': values['DB_PASSWORD'],
                'connect_timeout': 10, 'read_timeout': 30, 'write_timeout': 30})

    def test_invalid_environment_never_opens_connection(self):
        values = {'DB_HOST': 'localhost', 'DB_PORT': '3306', 'DB_NAME': 'cmdb',
                  'DB_USER': 'cmdb', 'DB_PASSWORD': 'test'}
        with patch('cmdb.interface.Database.DbMgr') as manager:
            for field, value in (('DB_PORT', '0'), ('DB_PORT', '65536'), ('DB_PORT', 'invalid'),
                                 ('DB_HOST', ''), ('DB_PASSWORD', '')):
                with self.subTest(field=field, value=value), patch.dict(os.environ, values | {field: value}, clear=True):
                    with self.assertRaises(ValueError):
                        connect_database()
            manager.assert_not_called()

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
