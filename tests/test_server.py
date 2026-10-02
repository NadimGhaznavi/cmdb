"""HTTP contracts and deployment entry point checks."""

from http.client import HTTPConnection
from cmdb.server.CmdbHTTPServer import CmdbHTTPServer
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
    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_status_history_is_shared_without_database_and_resets_on_restart(self, factory):
        messages = [f'Scanning 192.0.2.{number}' for number in range(8)]
        for message in messages:
            self.server.status_messages.append(message)
        self.server.status_messages.append('<script>alert(1)</script>\nNext line')
        expected = self.server.status_messages.snapshot()
        self.assertEqual([entry['message'] for entry in expected],
                         messages + ['<script>alert(1)</script> Next line'])
        for entry in expected:
            self.assertEqual(entry['source'], __name__)
            self.assertIsNotNone(datetime.fromisoformat(entry['timestamp']).tzinfo)
        for _ in range(2):
            connection = HTTPConnection(*self.server.server_address)
            try:
                connection.request('GET', '/status-messages')
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader('Cache-Control'), 'no-store')
                self.assertEqual(json.loads(response.read()), expected)
            finally:
                connection.close()
        factory.assert_not_called()
        with CmdbHTTPServer(('127.0.0.1', 0), CmdbHandler) as restarted:
            self.assertEqual(restarted.status_messages.snapshot(), [])

    def test_status_box_and_polling_assets_are_served(self):
        status, body = self.get('/')
        self.assertEqual(status, 200)
        self.assertIn(b'>Status Messages</h2>', body)
        self.assertIn(b'role="log"', body)
        self.assertIn(b'tabindex="0"', body)
        self.assertIn(b'<th scope="col">Timestamp</th><th scope="col">Source</th><th scope="col">Message</th>', body)
        self.assertIn(b'<tbody id="status-message-rows"></tbody>', body)
        self.assertIn(b'/static/status_messages.js', body)
        self.assertGreater(body.index(b'id="status-messages-title"'), body.rindex(b'</main>'))
        status, script = self.get('/static/status_messages.js')
        self.assertEqual(status, 200)
        self.assertIn(b'cell.textContent = value', script)
        self.assertIn(b"fetch('/status-messages'", script)
        status, styles = self.get('/static/machines.css')
        self.assertEqual(status, 200)
        self.assertIn(b'height: calc(9em + 2px)', styles)
        self.assertIn(b'overflow: auto', styles)

    def test_application_scan_queues_worker_and_reports_busy_or_unavailable(self):
        scanner = self.server.machine_scanner = Mock()
        scanner.request_scan.side_effect = [9, ValueError('Another scan is in progress.'),
                                           RuntimeError('Scanner is unavailable.')]
        for expected in (202, 409, 503):
            connection = HTTPConnection(*self.server.server_address)
            try:
                connection.request('POST', '/api/applications/scan')
                response = connection.getresponse()
                self.assertEqual(response.status, expected)
                body = json.loads(response.read())
                if expected == 202:
                    self.assertEqual(body, {'scanId': 9})
            finally:
                connection.close()
        self.assertTrue(all(call.kwargs == {'applications_only': True}
                            for call in scanner.request_scan.call_args_list))

    def setUp(self):
        self.server = CmdbHTTPServer(('127.0.0.1', 0), CmdbHandler)
        self.thread = Thread(target=self.server.serve_forever)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_registered_applications_lists_software_systems_and_closes_database(self, factory):
        records = [
            {'id': 1, 'name': 'MyCount', 'type': None, 'subtype': None, 'supplier': None, 'version': None},
            {'id': 2, 'name': None, 'type': 'OS', 'subtype': 'Debian', 'supplier': 'Debian', 'version': '13'},
        ]
        factory.return_value.query.return_value = records
        status, body = self.get('/api/applications')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {'applications': records})
        factory.return_value.close.assert_called_once()

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_registered_applications_database_failure_closes_and_hides_details(self, factory):
        factory.return_value.query.side_effect = pymysql.OperationalError('private failure')
        status, body = self.get('/api/applications')
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body), {'error': 'Registered applications are unavailable.'})
        factory.return_value.close.assert_called_once()

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_add_application_saves_name_without_deployment(self, factory):
        factory.return_value.insert.return_value = 42
        connection = HTTPConnection(*self.server.server_address)
        try:
            connection.request('POST', '/api/applications', json.dumps({'name': '  MyCount  '}),
                               {'Content-Type': 'application/json'})
            response = connection.getresponse()
            self.assertEqual(response.status, 201)
            self.assertEqual(json.loads(response.read()), {'id': 42, 'name': 'MyCount'})
        finally:
            connection.close()
        db = factory.return_value
        db.insert.assert_called_once_with('INSERT INTO ModelElement (namespace, name) VALUES (%s, %s)',
                                          (None, 'MyCount'))
        self.assertEqual([call.args[0] for call in db.execute.call_args_list], [
            'INSERT INTO Namespace (id) VALUES (%s)', 'INSERT INTO Package (id) VALUES (%s)',
            'INSERT INTO SoftwareSystem (id) VALUES (%s)'])
        db.transaction.return_value.__exit__.assert_called_once_with(None, None, None)
        db.close.assert_called_once()

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_add_application_rejects_invalid_names_before_database_access(self, factory):
        for values in ({}, [], {'name': None}, {'name': 7}, {'name': '   '},
                       {'name': 'x' * 256}, {'name': 'a\nb'}, {'name': 'App', 'machine': 7}):
            with self.subTest(values=values):
                connection = HTTPConnection(*self.server.server_address)
                try:
                    connection.request('POST', '/api/applications', json.dumps(values),
                                       {'Content-Type': 'application/json'})
                    response = connection.getresponse()
                    self.assertEqual(response.status, 400)
                    response.read()
                finally:
                    connection.close()
        factory.assert_not_called()

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_add_application_failure_exits_transaction_and_closes(self, factory):
        factory.return_value.execute.side_effect = pymysql.OperationalError('private failure')
        connection = HTTPConnection(*self.server.server_address)
        try:
            with self.assertLogs(level='ERROR'):
                connection.request('POST', '/api/applications', json.dumps({'name': 'MyCount'}),
                                   {'Content-Type': 'application/json'})
                response = connection.getresponse()
                self.assertEqual(response.status, 503)
                self.assertNotIn(b'private failure', response.read())
        finally:
            connection.close()
        self.assertIs(factory.return_value.transaction.return_value.__exit__.call_args.args[0],
                      pymysql.OperationalError)
        factory.return_value.close.assert_called_once()

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

    @patch('cmdb.server.CmdbHandler.SSH')
    @patch('cmdb.server.CmdbHandler.SoftwareDeploymentDb')
    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_uptime_only_contacts_known_debian_hosts(self, db, inventory, ssh):
        inventory.return_value.debian_hosts.return_value = [{'id': 7, 'ipAddress': '192.0.2.1'}]
        ssh.return_value.uptime.return_value = 90061
        status, body = self.get('/api/patching/hosts/7/uptime')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {'uptimeSeconds': 90061})
        ssh.return_value.uptime.assert_called_once_with('192.0.2.1')
        self.assertEqual(self.get('/api/patching/hosts/8/uptime')[0], 404)
        self.assertEqual(self.get('/api/patching/hosts/invalid/uptime')[0], 404)
        ssh.return_value.uptime.assert_called_once()
        ssh.return_value.uptime.side_effect = subprocess.TimeoutExpired('ssh', 10)
        self.assertEqual(self.get('/api/patching/hosts/7/uptime')[0], 503)

    @patch('cmdb.server.CmdbHandler.PatchScheduler')
    def test_patch_schedule_update_and_errors(self, scheduler):
        values = dict(machine=7, enabled=True, expression='15 2 * * 0')
        scheduler.return_value.update.return_value = dict(values, id=2)
        for failure, expected in [(None, 200), (ValueError('Invalid cron'), 400),
                                  (LookupError('not Debian'), 404), (OSError('cron failed'), 503)]:
            scheduler.return_value.update.side_effect = failure
            connection = HTTPConnection(*self.server.server_address)
            try:
                connection.request('POST', '/api/patch-schedules', json.dumps(values), {'Content-Type': 'application/json'})
                response = connection.getresponse()
                self.assertEqual(response.status, expected)
                response.read()
            finally:
                connection.close()
        scheduler.return_value.update.assert_called_with(**values)

    @patch('cmdb.server.CmdbHandler.DatabaseManager')
    def test_database_delete_confirmation_endpoint(self, manager):
        for values, failure, expected in [({'confirmation': 'app'}, None, 200),
                ({}, None, 400), ({'confirmation': 'cmdb'}, ValueError('This database cannot be deleted.'), 400),
                ({'confirmation': 'app'}, RuntimeError('Backup running'), 409)]:
            manager.return_value.delete.side_effect = failure
            connection = HTTPConnection(*self.server.server_address)
            try:
                connection.request('DELETE', '/api/databases/7', json.dumps(values), {'Content-Type': 'application/json'})
                response = connection.getresponse()
                self.assertEqual(response.status, expected)
                response.read()
            finally:
                connection.close()
        manager.return_value.delete.assert_any_call(7, 'app')

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

    def post_hostname(self, values, *, content_type='application/json', path='/api/machines/hostname'):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request('POST', path, json.dumps(values),
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
                                                   'pathname': 'sally/db/recorded.dump', 'sizeBytes': 1536}]
        with patch('cmdb.server.CmdbHandler.DCmdb.BACKUP_DIR', '/configured/backups'):
            status, body = self.get('/api/backups/files')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['files'][0]['backupTime'], '2026-09-28T14:00:00+00:00')
        self.assertEqual(json.loads(body)['files'][0]['filename'], 'recorded.dump')
        self.assertEqual(json.loads(body)['files'][0]['sizeBytes'], 1536)
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
        values = dict(modelElement=7, enabled=True, expression='0 12 * * *', retention='2-weeks')
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
                               (dict(modelElement=7, enabled=True, expression='0 12 * * *', retention='forever'), 503)]:
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

    @patch('cmdb.server.CmdbHandler.MachineDb')
    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_selected_machine_rescan(self, db, inventory):
        inventory.return_value.list_machines.return_value = [Mock(ipAddress='192.168.0.7')]
        scanner = self.server.machine_scanner = Mock()
        scanner.request_scan.return_value = 8
        for address, expected in [('192.168.0.7', 202), ('192.168.0.8', 404), ('invalid', 400)]:
            connection = HTTPConnection(*self.server.server_address)
            try:
                connection.request('POST', f'/api/machines/{address}/scan')
                response = connection.getresponse()
                self.assertEqual(response.status, expected)
                response.read()
            finally:
                connection.close()
        scanner.request_scan.assert_called_once_with('192.168.0.7')
        scanner.request_scan.side_effect = ValueError('Another scan is in progress.')
        connection = HTTPConnection(*self.server.server_address)
        try:
            connection.request('POST', '/api/machines/192.168.0.7/scan')
            response = connection.getresponse()
            self.assertEqual(response.status, 409)
            response.read()
        finally:
            connection.close()

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
    def test_save_machine_environment_and_clear_tag(self, factory):
        db = factory.return_value
        db.query.return_value = [{'id': 7}]
        for value in ('dev', 'qa', 'prod', 'unclassified'):
            with self.subTest(value=value):
                db.reset_mock()
                status, body = self.post_hostname({'machine': 7, 'environment': value},
                                                 path='/api/machines/environment')
                self.assertEqual((status, body), (200, {'environment': value}))
                db.query.assert_called_once_with('SELECT id FROM Machine WHERE id = %s FOR UPDATE', (7,))
                sql, params = db.execute.call_args.args
                if value == 'unclassified':
                    self.assertIn('DELETE FROM TaggedValue', sql)
                    self.assertEqual(params, (7, 'DeploymentEnvironment'))
                else:
                    self.assertIn('ON DUPLICATE KEY UPDATE', sql)
                    self.assertEqual(params, (7, 'DeploymentEnvironment', value))
                db.transaction.assert_called_once()
                db.close.assert_called_once()

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_invalid_environment_requests_do_not_open_database(self, factory):
        for values in ([], {}, {'machine': True, 'environment': 'prod'},
                       {'machine': 0, 'environment': 'prod'}, {'machine': 2**64, 'environment': 'prod'},
                       {'machine': '7', 'environment': 'prod'}, {'machine': 7, 'environment': 'Prod'},
                       {'machine': 7, 'environment': None}, {'machine': 7, 'environment': []},
                       {'machine': 7, 'environment': 'dev', 'extra': 1}):
            with self.subTest(values=values):
                self.assertEqual(self.post_hostname(values, path='/api/machines/environment')[0], 400)
        self.assertEqual(self.post_hostname({}, path='/api/machines/environment',
                                            content_type='text/plain')[0], 415)
        factory.assert_not_called()

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_environment_missing_machine_and_database_failure(self, factory):
        db = factory.return_value
        db.query.return_value = []
        values = {'machine': 7, 'environment': 'qa'}
        self.assertEqual(self.post_hostname(values, path='/api/machines/environment')[0], 404)
        db.execute.assert_not_called()
        db.close.assert_called_once()
        db.reset_mock()
        db.query.return_value = [{'id': 7}]
        db.execute.side_effect = pymysql.OperationalError('private details')
        status, body = self.post_hostname(values, path='/api/machines/environment')
        self.assertEqual(status, 503)
        self.assertNotIn('private details', json.dumps(body))
        db.close.assert_called_once()
        self.assertIs(db.transaction.return_value.__exit__.call_args.args[0], pymysql.OperationalError)

    @patch('cmdb.server.CmdbHandler.DbMgr', side_effect=pymysql.OperationalError('private details'))
    def test_environment_connection_failure(self, factory):
        status, body = self.post_hostname({'machine': 7, 'environment': 'dev'},
                                         path='/api/machines/environment')
        self.assertEqual(status, 503)
        self.assertNotIn('private details', json.dumps(body))

    @patch('cmdb.server.CmdbHandler.DbMgr')
    def test_save_hostname_updates_only_selected_machine(self, factory):
        factory.return_value.query.side_effect = [[{
            'id': 7, 'ipAddress': '192.168.0.7', 'hostName': 'worker.lan',
            'site': 'home',
            'createdOn': datetime(2026, 9, 27, 12), 'updatedOn': datetime(2026, 9, 27, 13),
        }], [], [], []]
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
            [{'id': 31, 'modelElement': 7, 'tag': 'DeploymentEnvironment', 'value': 'qa'}],
            [{'id': 22, 'machine': 7, 'subtype': 'MariaDB'}],
            [{'dataManager': 22, 'name': 'ax3l'}, {'dataManager': 22, 'name': 'r3el'}]]
        status, body = self.get('/api/machines')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['softwareDeployments'][0]['databases'], ['ax3l', 'r3el'])
        record = json.loads(body)['machines'][0]
        self.assertEqual(record['ipAddress'], '192.168.0.7')
        self.assertEqual(record['hostName'], '<script>host</script>')
        self.assertIsNone(record['site'])
        self.assertIsNone(record['reachable'])
        self.assertEqual(record['deployedComponent'], [21, 22])
        self.assertEqual(record['taggedValue'], [
            {'id': 31, 'modelElement': 7, 'tag': 'DeploymentEnvironment', 'value': 'qa'}])
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
                     '/pages/images/cmdb.png',
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
