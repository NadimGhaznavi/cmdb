"""Application discovery reads constants safely and records only valid installations."""

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase
from unittest.mock import Mock, patch

from cmdb.activity.ApplicationScanner import ApplicationScanner, application_version
from cmdb.entity.Machine import Machine
from cmdb.entity.StatusMessages import StatusMessages


class ApplicationVersionTests(TestCase):
    def test_module_and_class_literal_versions(self):
        self.assertEqual(application_version('VERSION = "1.2.3"'), '1.2.3')
        self.assertEqual(application_version('class MyCount:\n    VERSION: Final[str] = "1.2.3"'), '1.2.3')

    def test_invalid_and_executable_versions_are_not_evaluated(self):
        for source in ('', 'broken syntax!', 'VERSION = get_version()', 'VERSION = 3',
                       'VERSION = ""', 'VERSION = "a\\nb"',
                       'def f():\n    VERSION = "1.0"'):
            with self.subTest(source=source):
                self.assertIsNone(application_version(source))
        self.assertEqual(application_version('raise RuntimeError("never run")\nVERSION = "1.0"'), '1.0')


class ApplicationScannerTests(TestCase):
    def setUp(self):
        self.stop = Event()
        self.history = StatusMessages()
        self.worker = ApplicationScanner(self.stop, self.history)
        self.worker._ssh = Mock()
        self.worker._ssh.run.return_value.stdout = 'class MyCount:\n    VERSION = "1.2.3"'
        for name in ('DbMgr', 'MachineDb', 'SoftwareSystemDb', 'SoftwareDeploymentDb'):
            patcher = patch('cmdb.activity.ApplicationScanner.' + name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)
        self.SoftwareSystemDb.return_value.list_applications.return_value = [{'id': 17, 'name': 'MyCount'}]
        self.MachineDb.return_value.list_machines.return_value = []

    def test_status_messages_use_short_lowercase_hostname_for_all_outcomes(self):
        self.MachineDb.return_value.list_machines.return_value = [
            Machine('192.0.2.7', id=7, hostName='SALLY.Example.COM')]
        self.worker._ssh.run.side_effect = [Mock(stdout='VERSION = "1.2.3"'),
                                           Mock(stdout=''), subprocess.TimeoutExpired('ssh', 30)]
        self.worker.run({'192.0.2.7': 7})
        self.worker.run({'192.0.2.7': 7})
        with self.assertRaises(OSError):
            self.worker.run({'192.0.2.7': 7})
        self.assertEqual([entry['message'] for entry in self.history.snapshot()], [
            'sally: MyCount 1.2.3', 'sally: MyCount — not detected.',
            'sally: MyCount — read failed.'])
        self.assertTrue(all(call.args[0] == '192.0.2.7'
                            for call in self.worker._ssh.run.call_args_list))

    def test_status_messages_fall_back_to_ip_without_hostname(self):
        for hostname in (None, ''):
            with self.subTest(hostname=hostname):
                self.MachineDb.return_value.list_machines.return_value = [
                    Machine('192.0.2.7', id=7, hostName=hostname)]
                self.worker.run({'192.0.2.7': 7})
                self.assertEqual(self.history.snapshot()[-1]['message'],
                                 '192.0.2.7: MyCount 1.2.3')

    def test_installed_application_uses_convention_and_writes_after_command(self):
        def run(address, command, **kwargs):
            self.DbMgr.return_value.close.assert_called_once()
            self.assertIn('[ -d /opt/prod/mycount ]', command)
            self.assertIn('/opt/prod/mycount/mycount/constants/DMyCount.py', command)
            self.assertNotIn('/opt/prod/mycount/mycount/constants/MyCount.py', command)
            self.assertNotIn('/opt/dev', command)
            self.assertEqual(address, '192.0.2.7')
            return Mock(stdout='VERSION = "1.2.3"')
        self.worker._ssh.run.side_effect = run
        self.worker.run({'192.0.2.7': 7})
        self.SoftwareDeploymentDb.return_value.record_application.assert_called_once_with(
            7, 17, '/opt/prod/mycount', '1.2.3')
        self.DbMgr.return_value.transaction.return_value.__exit__.assert_called_once_with(None, None, None)
        self.assertEqual(self.DbMgr.return_value.close.call_count, 2)
        entries = self.history.snapshot()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['source'], 'cmdb.activity.ApplicationScanner')
        self.assertEqual(entries[0]['message'], '192.0.2.7: MyCount 1.2.3')

    def test_missing_directory_file_or_version_preserves_inventory(self):
        for source in ('', 'OTHER = "1.2.3"', 'VERSION = ""'):
            self.worker._ssh.run.return_value.stdout = source
            self.worker.run({'192.0.2.7': 7})
        self.SoftwareDeploymentDb.assert_not_called()
        self.assertEqual([entry['message'] for entry in self.history.snapshot()],
                         ['192.0.2.7: MyCount — not detected.'] * 3)

    def test_real_directory_and_constants_file_are_required(self):
        def run(address, command, **kwargs):
            return subprocess.run(['/bin/sh', '-c', command], capture_output=True,
                                  text=True, check=True, timeout=5)
        self.worker._ssh.run.side_effect = run
        with TemporaryDirectory() as root, patch('cmdb.activity.ApplicationScanner.DCmdb.BASE_INSTALL_DIR', root):
            self.worker.run({'192.0.2.7': 7})
            constants = Path(root) / 'mycount' / 'mycount' / 'constants' / 'DMyCount.py'
            constants.parent.mkdir(parents=True)
            self.worker.run({'192.0.2.7': 7})
            constants.write_text('OTHER = "1.2.3"')
            self.worker.run({'192.0.2.7': 7})
            self.SoftwareDeploymentDb.assert_not_called()
            constants.write_text('class MyCount:\n    VERSION: Final[str] = "1.2.3"')
            self.worker.run({'192.0.2.7': 7})
            self.SoftwareDeploymentDb.return_value.record_application.assert_called_once_with(
                7, 17, str(Path(root) / 'mycount'), '1.2.3')

    def test_only_prefixed_constants_are_used(self):
        def run(address, command, **kwargs):
            return subprocess.run(['/bin/sh', '-c', command], capture_output=True,
                                  text=True, check=True, timeout=5)
        self.worker._ssh.run.side_effect = run
        with TemporaryDirectory() as root, patch('cmdb.activity.ApplicationScanner.DCmdb.BASE_INSTALL_DIR', root):
            constants = Path(root) / 'mycount' / 'mycount' / 'constants' / 'DMyCount.py'
            constants.parent.mkdir(parents=True)
            constants.with_name('MyCount.py').write_text('VERSION = "1.2.3"')
            self.worker.run({'192.0.2.7': 7})
            self.SoftwareDeploymentDb.assert_not_called()
            constants.write_text('class DMyCount:\n    VERSION: Final[str] = "0.13.2"')
            self.worker.run({'192.0.2.7': 7})
            records = self.SoftwareDeploymentDb.return_value.record_application
            records.assert_called_once_with(7, 17, str(Path(root) / 'mycount'), '0.13.2')
            records.reset_mock()
            constants.write_text('VERSION = get_version()')
            self.worker.run({'192.0.2.7': 7})
            records.assert_not_called()

    def test_host_failure_continues_other_hosts_and_reports_partial_failure(self):
        self.worker._ssh.run.side_effect = [subprocess.TimeoutExpired('ssh', 30),
                                           Mock(stdout='VERSION = "1.2.3"')]
        with self.assertRaises(OSError):
            self.worker.run({'192.0.2.7': 7, '192.0.2.8': 8})
        self.SoftwareDeploymentDb.return_value.record_application.assert_called_once_with(
            8, 17, '/opt/prod/mycount', '1.2.3')
        self.assertEqual([entry['message'] for entry in self.history.snapshot()], [
            '192.0.2.7: MyCount — read failed.', '192.0.2.8: MyCount 1.2.3'])

    def test_unsafe_names_and_stopped_scans_run_no_commands(self):
        self.SoftwareSystemDb.return_value.list_applications.return_value = [
            {'id': 17, 'name': '../escape'}, {'id': 18, 'name': 'My Count'}]
        self.worker.run({'192.0.2.7': 7})
        self.stop.set()
        self.worker.run({'192.0.2.7': 7})
        self.worker._ssh.run.assert_not_called()

    def test_stop_after_read_prevents_write(self):
        def run(*args, **kwargs):
            self.stop.set()
            return Mock(stdout='VERSION = "1.2.3"')
        self.worker._ssh.run.side_effect = run
        self.worker.run({'192.0.2.7': 7})
        self.SoftwareDeploymentDb.assert_not_called()
