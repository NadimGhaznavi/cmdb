"""HTTP contracts and deployment entry point checks."""

from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import Mock, patch

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

    def post_hostname(self, values, *, content_type='application/json'):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request('POST', '/api/machines/hostname', json.dumps(values),
                               {'Content-Type': content_type})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_refresh_signals_server_worker_and_exposes_completion(self):
        scanner = self.server.machine_scanner = Mock()
        scanner.request_scan.return_value = 7
        scanner.scan_status.return_value = {
            'scanId': 7, 'completedScanId': 6, 'running': True, 'error': None,
        }
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request('POST', '/api/scan')
            response = connection.getresponse()
            self.assertEqual(response.status, 202)
            self.assertEqual(json.loads(response.read()), {'scanId': 7})
        finally:
            connection.close()
        scanner.request_scan.assert_called_once()
        status, body = self.get('/api/scan')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), scanner.scan_status.return_value)

    def test_scan_endpoints_return_503_without_a_worker(self):
        self.assertEqual(self.get('/api/scan')[0], 503)
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request('POST', '/api/scan')
            response = connection.getresponse()
            self.assertEqual(response.status, 503)
            response.read()
        finally:
            connection.close()

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_save_hostname_updates_only_selected_machine(self, factory):
        factory.return_value.query.side_effect = [[{
            'id': 7, 'ipAddress': '192.168.0.7', 'hostName': 'worker.lan',
            'site': 'home',
            'createdOn': datetime(2026, 9, 27, 12), 'updatedOn': datetime(2026, 9, 27, 13),
        }], [], []]
        status, body = self.post_hostname({'ipAddress': '192.168.0.7', 'hostName': ' worker.lan '})
        self.assertEqual(status, 200)
        self.assertEqual(body['machine']['hostName'], 'worker.lan')
        self.assertEqual(body['machine']['updatedOn'], '2026-09-27T13:00:00+00:00')
        self.assertEqual(factory.return_value.execute.call_args.args[1], ('worker.lan', '192.168.0.7'))
        factory.return_value.transaction.assert_called_once()
        factory.return_value.close.assert_called_once()

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_empty_hostname_clears_value_and_missing_machine_is_404(self, factory):
        factory.return_value.query.return_value = []
        status, body = self.post_hostname({'ipAddress': '192.168.0.7', 'hostName': ''})
        self.assertEqual(status, 404)
        self.assertEqual(factory.return_value.execute.call_args.args[1], (None, '192.168.0.7'))
        factory.return_value.close.assert_called_once()

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_invalid_hostname_requests_do_not_open_database(self, factory):
        for values in ([], {}, {'ipAddress': 'invalid', 'hostName': 'worker'},
                       {'ipAddress': '192.168.0.7', 'hostName': None},
                       {'ipAddress': '192.168.0.7', 'hostName': 'x' * 256},
                       {'ipAddress': '192.168.0.7', 'hostName': 'worker', 'site': 'other'}):
            with self.subTest(values=values):
                self.assertEqual(self.post_hostname(values)[0], 400)
        self.assertEqual(self.post_hostname({}, content_type='text/plain')[0], 415)
        factory.assert_not_called()

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_hostname_save_failure_closes_connection_and_returns_error(self, factory):
        factory.return_value.execute.side_effect = pymysql.OperationalError('private details')
        status, body = self.post_hostname({'ipAddress': '192.168.0.7', 'hostName': 'worker'})
        self.assertEqual(status, 503)
        self.assertNotIn('private details', json.dumps(body))
        factory.return_value.close.assert_called_once()
        self.assertIs(factory.return_value.transaction.return_value.__exit__.call_args.args[0],
                      pymysql.OperationalError)

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

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_machine_records_include_nullable_fields_and_utc_timestamps(self, factory):
        factory.return_value.query.side_effect = [[{
            'id': 7, 'ipAddress': '192.168.0.7', 'hostName': '<script>host</script>',
            'site': None,
            'createdOn': datetime(2026, 9, 27, 12, 0), 'updatedOn': datetime(2026, 9, 27, 13, 0),
        }], [{'id': 21, 'machine': 7}, {'id': 22, 'machine': 7}],
            [{'id': 21, 'namespace': 7}, {'id': 22, 'namespace': 7}], []]
        status, body = self.get('/api/machines')
        self.assertEqual(status, 200)
        record = json.loads(body)['machines'][0]
        self.assertEqual(record['ipAddress'], '192.168.0.7')
        self.assertEqual(record['hostName'], '<script>host</script>')
        self.assertIsNone(record['site'])
        self.assertEqual(record['deployedComponent'], [21, 22])
        self.assertEqual(record['createdOn'], '2026-09-27T12:00:00+00:00')
        self.assertEqual(record['updatedOn'], '2026-09-27T13:00:00+00:00')
        factory.return_value.close.assert_called_once()

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_empty_machine_inventory(self, factory):
        factory.return_value.query.return_value = []
        status, body = self.get('/api/machines')
        self.assertEqual((status, json.loads(body)), (200, {'machines': [], 'softwareDeployments': []}))
        factory.return_value.close.assert_called_once()

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_machine_query_failure_closes_connection_and_hides_details(self, factory):
        factory.return_value.query.side_effect = pymysql.OperationalError('private details')
        status, body = self.get('/api/machines')
        self.assertEqual(status, 503)
        self.assertNotIn(b'private details', body)
        factory.return_value.close.assert_called_once()

    @patch('cmdb.server.CmdbHandler.DbMgr', side_effect=pymysql.OperationalError('private details'))
    def test_machine_connection_failure_is_503(self, factory):
        status, body = self.get('/api/machines')
        self.assertEqual(status, 503)
        self.assertNotIn(b'private details', body)

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_local_graph_assets_and_unlisted_paths(self, factory):
        for path in ('/static/machines.css', '/static/machines.js',
                     '/static/vendor/cytoscape-3.34.3.min.js'):
            with self.subTest(path=path):
                status, body = self.get(path)
                self.assertEqual(status, 200)
                self.assertTrue(body)
        self.assertEqual(self.get('/static/../CmdbHandler.py')[0], 404)
        factory.assert_not_called()


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
