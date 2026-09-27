"""HTTP contracts and deployment entry point checks."""

from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

import pymysql

from cmdb.server.CmdbHandler import CmdbHandler


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), CmdbHandler)
        self.thread = Thread(target=self.server.serve_forever)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def get(self, path):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request('GET', path)
            response = connection.getresponse()
            body = response.read()
            self.assertEqual(int(response.getheader('Content-Length')), len(body))
            return response.status, body
        finally:
            connection.close()

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_home_health_and_missing_page_do_not_query_database(self, factory):
        status, body = self.get('/')
        self.assertEqual(status, 200)
        self.assertIn(b'Configuration Management Database', body)
        status, body = self.get('/health')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {'status': 'ok', 'service': 'cmdb-server'})
        self.assertEqual(self.get('/missing')[0], 404)
        factory.assert_not_called()

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_readiness_queries_and_closes_database(self, factory):
        status, body = self.get('/ready')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['status'], 'ready')
        factory.return_value.query.assert_called_once_with('SELECT 1 AS ready')
        factory.return_value.close.assert_called_once()

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_database_failure_is_503_and_connection_is_closed(self, factory):
        factory.return_value.query.side_effect = pymysql.OperationalError('private details')
        with self.assertLogs(level='ERROR'):
            status, body = self.get('/ready')
        self.assertEqual(status, 503)
        self.assertNotIn(b'private details', body)
        factory.return_value.close.assert_called_once()

    @patch('cmdb.server.CmdbHandler.DbMgr', side_effect=pymysql.OperationalError('connection failed'))
    def test_connection_failure_is_503(self, factory):
        with self.assertLogs(level='ERROR'):
            self.assertEqual(self.get('/ready')[0], 503)


class DeploymentTests(unittest.TestCase):
    def test_entry_point_works_outside_checkout(self):
        root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as directory:
            shutil.copytree(root / 'cmdb', Path(directory, 'cmdb'))
            shutil.copy2(root / 'cmdb-server.py', directory)
            result = subprocess.run([sys.executable, '-B', 'cmdb-server.py', '--help'],
                                    cwd=directory, capture_output=True, text=True, check=True)
            self.assertIn('--port', result.stdout)
            result = subprocess.run([sys.executable, '-B', 'cmdb-server.py', '--port', '65536'],
                                    cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('--port must be', result.stderr)
