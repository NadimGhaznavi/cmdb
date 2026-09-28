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

    @patch('cmdb.server.CmdbHandler.PatchDb')
    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_patching_hosts_and_queue(self, db, records):
        records.return_value.hosts.return_value = [{'id': 7, 'hostName': 'debian.example', 'job': None}]
        status, body = self.get('/api/patching/hosts')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['hosts'][0]['id'], 7)
        records.return_value.report.return_value = [{'id': 12, 'patchTime': datetime(2026, 9, 28, 12), 'elapsedSeconds': 90}]
        status, body = self.get('/api/patching/report')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['runs'][0]['patchTime'], '2026-09-28T12:00:00+00:00')
        records.return_value.request.return_value = 12
        for values, expected in [({'machine': 7}, 202), ({'machine': True}, 400), ({'machine': -1}, 400)]:
            connection = HTTPConnection(*self.server.server_address)
            try:
                connection.request('POST', '/api/patching', json.dumps(values), {'Content-Type': 'application/json'})
                response = connection.getresponse()
                self.assertEqual(response.status, expected)
                response.read()
            finally:
                connection.close()
        records.return_value.request.assert_called_once_with(7)

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

    def test_backup_post_validates_target_and_returns_attempt_id(self):
        manager = self.server.backup_manager = Mock()
        manager.request_backup.return_value = 42
        for payload, expected in [({'modelElement': 7}, 202), ({'modelElement': True}, 400),
                                  ({'modelElement': -1}, 400), ({'modelElement': 0}, 400),
                                  ({'modelElement': 7, 'pathname': '/tmp/unsafe'}, 400)]:
            with self.subTest(payload=payload):
                connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
                try:
                    connection.request('POST', '/api/backups', json.dumps(payload), {'Content-Type': 'application/json'})
                    response = connection.getresponse()
                    self.assertEqual(response.status, expected)
                    body = json.loads(response.read())
                    if expected == 202:
                        self.assertEqual(body, {'backupId': 42})
                finally:
                    connection.close()
        manager.request_backup.assert_called_once_with(7)

    @patch('cmdb.server.CmdbHandler.BackupDb')
    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_backup_get_serializes_timestamps_and_missing_attempt(self, db, records):
        records.return_value.databases.return_value = [{'modelElement': 7, 'lastBackup': datetime(2026, 9, 28, 14)}]
        records.return_value.hosts.return_value = []
        status, body = self.get('/api/backups')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['databases'][0]['lastBackup'], '2026-09-28T14:00:00+00:00')
        records.return_value.files.return_value = [{'id': 42, 'backupTime': datetime(2026, 9, 28, 14),
                                                   'hostName': 'sally.example', 'databaseName': 'cmdb',
                                                   'pathname': 'sally/db/recorded.dump'}]
        with patch('cmdb.server.CmdbHandler.DCmdb.BACKUP_DIR', '/configured/backups'):
            status, body = self.get('/api/backups/files')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['files'][0]['backupTime'], '2026-09-28T14:00:00+00:00')
        self.assertEqual(json.loads(body)['files'][0]['filename'], 'recorded.dump')
        self.assertEqual(json.loads(body)['directory'], '/configured/backups')
        records.return_value.get.assert_not_called()
        records.return_value.get.return_value = None
        self.assertEqual(self.get('/api/backups/42')[0], 404)
        self.assertEqual(self.get('/api/backups/invalid')[0], 404)

    @patch('cmdb.server.CmdbHandler.BackupFiles')
    @patch('cmdb.server.CmdbHandler.BackupDb')
    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_vault_scan_and_delete_only_missing_records(self, db, records, files):
        records.return_value.files.return_value = [{'id': 42, 'pathname': 'host/db/db/file.dump'}]
        records.return_value.get.return_value = dict(id=42, status='succeeded', pathname='host/db/db/file.dump')
        for method, path, statuses, expected in [
            ('POST', '/api/backups/files/scan', ['Missing'], 200),
            ('DELETE', '/api/backups/files/42', ['Found'], 409),
            ('DELETE', '/api/backups/files/42', PermissionError('denied'), 503),
            ('DELETE', '/api/backups/files/42', ['Missing'], 200),
        ]:
            files.return_value.scan.side_effect = statuses if isinstance(statuses, Exception) else None
            files.return_value.scan.return_value = statuses
            connection = HTTPConnection(*self.server.server_address)
            try:
                connection.request(method, path)
                response = connection.getresponse()
                self.assertEqual(response.status, expected)
                result = json.loads(response.read())
                if method == 'POST':
                    self.assertEqual(result, {'files': [{'id': 42, 'status': 'Missing'}]})
                if expected != 200:
                    records.return_value.delete.assert_not_called()
            finally:
                connection.close()
        records.return_value.delete.assert_called_once_with(42)

    @patch('cmdb.server.CmdbHandler.Scheduler')
    def test_schedule_update_and_delete(self, scheduler):
        values = dict(modelElement=7, enabled=True, frequency='daily', retention='2-weeks')
        scheduler.return_value.update.return_value = dict(id=12, **values)
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request('POST', '/api/backup-schedules', json.dumps(values), {'Content-Type': 'application/json'})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())['schedule']['id'], 12)
            scheduler.return_value.update.assert_called_once_with(**values)
            connection.request('DELETE', '/api/backup-schedules/12')
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            scheduler.return_value.delete.assert_called_once_with(12)
        finally:
            connection.close()

    @patch('cmdb.server.CmdbHandler.Scheduler')
    def test_invalid_schedule_body_and_cron_error(self, scheduler):
        for values, status in [({'modelElement': 7}, 400),
                               (dict(modelElement=7, enabled=True, frequency='daily', retention='forever'), 503)]:
            scheduler.return_value.update.side_effect = OSError('cron denied')
            connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
            try:
                connection.request('POST', '/api/backup-schedules', json.dumps(values), {'Content-Type': 'application/json'})
                response = connection.getresponse()
                self.assertEqual(response.status, status)
                self.assertIn('error', json.loads(response.read()))
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
            [{'id': 21, 'namespace': 7}, {'id': 22, 'namespace': 7}],
            [{'id': 22, 'machine': 7, 'subtype': 'MariaDB'}],
            [{'dataManager': 22, 'name': 'ax3l'}, {'dataManager': 22, 'name': 'r3el'}]]
        status, body = self.get('/api/machines')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['softwareDeployments'][0]['databases'], ['ax3l', 'r3el'])
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
