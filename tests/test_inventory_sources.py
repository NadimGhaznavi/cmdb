"""Source boundaries: collect observations without database writes or code execution."""

import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase
from unittest.mock import Mock, patch

import nmap

from cmdb.activity.sources.ApplicationSource import ApplicationSource, application_databases, application_components, application_metadata, application_version
from cmdb.activity.sources.HostSource import HostSource
from cmdb.activity.sources.MariaDBSource import MariaDBSource
from cmdb.activity.sources.NetworkSource import NetworkSource
from cmdb.activity.sources.NmapOSSource import NmapOSSource
from cmdb.constants.DCMDB import DCMDB
from cmdb.entity.SoftwareSystem import SoftwareSystem
from cmdb.entity.TaggedValue import TaggedValue


def result(stdout=''):
    return subprocess.CompletedProcess(['ssh'], 0, stdout, '')


def denied():
    return subprocess.CalledProcessError(255, ['ssh'], stderr='Permission denied (publickey).')


class ApplicationSourceTests(TestCase):
    def test_metadata_is_literal_optional_and_never_executed(self):
        source = ('raise RuntimeError("never run")\n'
                  'class App:\n'
                  '    VERSION: Final[str] = "1.2.3"\n'
                  '    CMDB_TYPE = " application "\n'
                  '    CMDB_SUBTYPE = "inventory"\n'
                  '    CMDB_SUPPLIER = "Example Supplier"\n'
                  '    CMDB_CODENAME = "Orion"\n')
        self.assertEqual(application_metadata(source), SoftwareSystem(
            version='1.2.3', type='application', subtype='inventory', supplier='Example Supplier',
            taggedValue=[TaggedValue(tag='VERSION_CODENAME', value='Orion')]))
        for value in ('get_type()', '3', 'None', '""', '"a\\nb"', repr('x' * 256)):
            with self.subTest(value=value):
                self.assertEqual(application_metadata('VERSION = "1.0"\nCMDB_TYPE = ' + value),
                                 SoftwareSystem(version='1.0'))
        self.assertIsNone(application_metadata('CMDB_TYPE = "application"'))
        self.assertEqual(application_metadata('VERSION = "1.0"\ndef f():\n    CMDB_TYPE = "ignored"'),
                         SoftwareSystem(version='1.0'))

    def test_components_are_literal_validated_and_deduplicated(self):
        source = ('raise RuntimeError("never run")\nclass App:\n'
                  '    CMDB_COMPONENTS: tuple = ((" Marketing Screenshots ", "pages/marketing"), '
                  '("Uploads", "/srv/uploads"), ("Marketing Screenshots", "pages/marketing"))')
        self.assertEqual(application_components(source),
                         (("Marketing Screenshots", "pages/marketing"), ("Uploads", "/srv/uploads")))
        for declaration in ('get_components()', '"path"', 'None', '(("name",),)',
                            '((3, "path"),)', '(("", "path"),)', '(("name", "../escape"),)',
                            '(("name", "a/../escape"),)', '(("name", "."),)', '(("name", "./"),)',
                            repr((("x" * 256, "path"),)), repr((("name", "a\nb"),))):
            with self.subTest(declaration=declaration):
                self.assertEqual(application_components('CMDB_COMPONENTS = ' + declaration), ())
        self.assertEqual(application_components('def f():\n    CMDB_COMPONENTS = (("name", "path"),)'), ())
        self.assertEqual(application_components('broken syntax!'), ())
        self.assertEqual(application_components('CMDB_COMPONENTS = [("good", "path"), ("bad", 3)]'),
                         (("good", "path"),))

    def test_databases_are_literal_validated_and_case_preserving(self):
        source = ('raise RuntimeError("never run")\nclass App:\n'
                  '    CMDB_DATABASES: tuple = (("MyCount", "mycount"), '
                  '("MyCount", "mycount"), ("Other", "MyCount"))')
        self.assertEqual(application_databases(source), (("MyCount", "mycount"), ("Other", "MyCount")))
        for declaration in ('get_databases()', 'None', '"mycount"', '(("name",),)',
                            '(("", "db"),)', '((3, "db"),)', '(("name", "a\\nb"),)',
                            repr((("name", "x" * 65),))):
            with self.subTest(declaration=declaration):
                self.assertEqual(application_databases('CMDB_DATABASES = ' + declaration), ())
        self.assertEqual(application_databases('def f():\n    CMDB_DATABASES = (("x", "db"),)'), ())
        source = ApplicationSource()
        source._ssh = Mock()
        source._ssh.run.return_value = result('VERSION = "1.0"\nCMDB_DATABASES = (("MyCount", "mycount"),)')
        self.assertEqual(source.collect('192.0.2.7', 'MyCount')[-1], (("MyCount", "mycount"),))

    def test_literal_versions_are_parsed_without_execution(self):
        for source in ('VERSION = "1.2.3"', 'class App:\n    VERSION: Final[str] = "1.2.3"',
                       'raise RuntimeError("never run")\nVERSION = "1.2.3"'):
            self.assertEqual(application_version(source), '1.2.3')
        for source in ('', 'broken syntax!', 'VERSION = get_version()', 'VERSION = 3',
                       'VERSION = ""', 'VERSION = "a\\nb"', 'def f():\n    VERSION = "1.0"'):
            self.assertIsNone(application_version(source))

    def test_directory_and_prefixed_constants_are_required(self):
        source = ApplicationSource()
        source._ssh = Mock()
        source._ssh.run.side_effect = lambda address, command, **kwargs: subprocess.run(
            ['/bin/sh', '-c', command], capture_output=True, text=True, check=True, timeout=5)
        with TemporaryDirectory() as root, patch.object(DCMDB, 'BASE_INSTALL_DIR', root):
            self.assertEqual(source.collect('192.0.2.7', 'MyCount')[0], 'not detected')
            constants = Path(root) / 'mycount/mycount/constants/DMyCount.py'
            constants.parent.mkdir(parents=True)
            (constants.parent / 'MyCount.py').write_text('VERSION = "wrong file"')
            self.assertEqual(source.collect('192.0.2.7', 'MyCount')[0], 'not detected')
            constants.write_text('class App:\n    VERSION = "1.2.3"\n    CMDB_COMPONENTS = (("Screenshots", "pages/marketing"),)')
            self.assertEqual(source.collect('192.0.2.7', 'MyCount'),
                             ('observed', str(Path(root) / 'mycount'), SoftwareSystem(version='1.2.3'), (('Screenshots', 'pages/marketing'),), ()))

    def test_cmdb_convention_and_failed_read(self):
        source = ApplicationSource()
        source._ssh = Mock()
        source._ssh.run.return_value = result(Path('cmdb/constants/DCMDB.py').read_text())
        outcome, pathname, system, components, databases = source.collect('192.0.2.7', 'CMDB')
        self.assertEqual((outcome, pathname), ('observed', '/opt/prod/cmdb'))
        self.assertEqual(system.version, DCMDB.VERSION)
        self.assertEqual(system.type, DCMDB.CMDB_TYPE)
        self.assertEqual(system.subtype, DCMDB.CMDB_SUBTYPE)
        self.assertEqual(system.supplier, DCMDB.CMDB_SUPPLIER)
        self.assertEqual(system.taggedValue,
                         [TaggedValue(tag='VERSION_CODENAME', value=DCMDB.CMDB_CODENAME)])
        self.assertIn('/opt/prod/cmdb/cmdb/constants/DCMDB.py', source._ssh.run.call_args.args[1])
        source._ssh.run.side_effect = subprocess.TimeoutExpired('ssh', 30)
        self.assertEqual(source.collect('192.0.2.7', 'CMDB')[0], 'read failed')

    def test_unsafe_names_run_no_commands(self):
        source = ApplicationSource()
        source._ssh = Mock()
        for name in ('../escape', 'My Count'):
            self.assertEqual(source.collect('192.0.2.7', name), ('unsupported name', None, None, (), ()))
        source._ssh.run.assert_not_called()


class HostSourceTests(TestCase):
    def setUp(self):
        self.stop = Event()
        self.source = HostSource(self.stop)
        self.source._ssh = Mock()
        self.source._ssh.is_local.return_value = False
        self.remote = self.source._ssh.run
        self.port = patch('cmdb.activity.sources.HostSource.socket.create_connection').start()
        self.addCleanup(patch.stopall)
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        key = Path(directory.name) / 'id_ed25519'
        Path(str(key) + '.pub').write_text('ssh-ed25519 AAAATEST cmdb\n')
        patch.object(DCMDB, 'SSH_KEY', str(key)).start()

    def test_remote_provisioning_retests_agent_before_collection(self):
        self.remote.side_effect = [denied(), result(), result(), result('worker'), result('[]'), result('')]
        self.assertTrue(self.source.ensure_access('192.0.2.7'))
        observation = self.source.collect('192.0.2.7')
        self.assertEqual(observation['hostname'], 'worker')
        calls = self.remote.call_args_list
        self.assertEqual(calls[1].kwargs['user'], 'root')
        self.assertIn('authorized_keys', calls[1].kwargs['input'])
        self.assertEqual(calls[2].args[1], 'true')
        self.assertNotIn('user', calls[2].kwargs)

    def test_local_access_skips_port_and_never_provisions(self):
        self.source._ssh.is_local.return_value = True
        self.remote.side_effect = denied()
        with self.assertRaises(subprocess.CalledProcessError):
            self.source.ensure_access('192.0.2.7')
        self.port.assert_not_called()
        self.remote.assert_called_once()

    def test_changed_key_and_closed_port_do_not_provision(self):
        self.remote.side_effect = subprocess.CalledProcessError(
            255, ['ssh'], stderr='REMOTE HOST IDENTIFICATION HAS CHANGED')
        self.assertFalse(self.source.ensure_access('192.0.2.7'))
        self.remote.assert_called_once()
        self.remote.reset_mock()
        self.port.side_effect = ConnectionRefusedError()
        with self.assertRaises(ConnectionRefusedError):
            self.source.ensure_access('192.0.2.7')
        self.remote.assert_not_called()

    def test_mac_matches_scanned_interface_and_host_os_is_parsed(self):
        interfaces = [{'link_type': 'ether', 'address': 'aa:bb:cc:dd:ee:01',
                       'addr_info': [{'local': '10.0.0.1'}]},
                      {'link_type': 'ether', 'address': 'aa:bb:cc:dd:ee:02',
                       'addr_info': [{'local': '192.0.2.7'}]}]
        self.remote.side_effect = [result('worker'), result(json.dumps(interfaces)),
                                   result('ID=debian\nVERSION_ID=13')]
        observation = self.source.collect('192.0.2.7')
        self.assertEqual(observation['mac_address'], 'AA:BB:CC:DD:EE:02')
        self.assertEqual(observation['system'].version, '13')

    def test_optional_read_failures_preserve_valid_hostname(self):
        self.remote.side_effect = [result('worker'), subprocess.CalledProcessError(127, ['ip']),
                                   subprocess.TimeoutExpired('cat', 30)]
        self.assertEqual(self.source.collect('192.0.2.7'),
                         {'hostname': 'worker', 'mac_address': None, 'system': None})

    def test_invalid_hostname_stops_collection(self):
        for value in ('', 'banner\nhost', 'x' * 256):
            self.remote.reset_mock()
            self.remote.side_effect = [result(value)]
            self.assertIsNone(self.source.collect('192.0.2.7'))
            self.remote.assert_called_once()

    def test_shutdown_stops_commands(self):
        self.stop.set()
        with self.assertRaises(InterruptedError):
            self.source.collect('192.0.2.7')
        self.remote.assert_not_called()


class NmapSourceTests(TestCase):
    @patch('cmdb.activity.sources.NetworkSource.Nmap')
    def test_discovery_ignores_dns_and_down_hosts(self, scanner):
        scanner.return_value.scan.return_value = {'nmap': {'scaninfo': {}}, 'scan': {
            '192.0.2.7': {'status': {'state': 'up'}, 'addresses': {'mac': 'AA:BB:CC:DD:EE:FF'},
                          'hostnames': [{'name': 'ignore'}]},
            '192.0.2.8': {'status': {'state': 'down'}}}}
        machines = NetworkSource().collect('192.0.2.0/24')
        self.assertEqual(len(machines), 1)
        self.assertIsNone(machines[0].hostName)
        self.assertEqual(machines[0].macAddress, 'AA:BB:CC:DD:EE:FF')
        self.assertEqual(scanner.return_value.scan.call_args.kwargs['arguments'], '-sn -n')
        scanner.return_value.scan.return_value['nmap']['scaninfo']['error'] = ['failed']
        with self.assertRaises(nmap.PortScannerError):
            NetworkSource().collect('192.0.2.0/24')

    @patch('cmdb.activity.sources.NmapOSSource.Nmap')
    def test_os_scope_and_exact_classification(self, scanner):
        host = {'status': {'state': 'up'}, 'osmatch': [{'accuracy': '100', 'osclass': [
            {'accuracy': '100', 'osfamily': 'Linux', 'vendor': 'Linux', 'osgen': '6.X'}]}]}
        scanner.return_value.scan.return_value = {'nmap': {'scaninfo': {}}, 'scan': {
            '192.0.2.7': host, '192.0.2.8': host}}
        observations = NmapOSSource().collect(['192.0.2.7'])
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0][0], '192.0.2.7')
        self.assertEqual(observations[0][1].version, '6.X')
        scanner.reset_mock()
        self.assertEqual(NmapOSSource().collect([]), [])
        scanner.assert_not_called()

    @patch('cmdb.activity.sources.MariaDBSource.SSHDb')
    def test_mariadb_returns_complete_observation(self, database):
        observation = {'version': '11.8-MariaDB', 'pathname': '/var/lib/mysql/', 'databases': ['cmdb']}
        database.return_value.inventory.return_value = observation
        self.assertEqual(MariaDBSource(Event()).collect('192.0.2.7'), observation)
        database.return_value.inventory.assert_called_once_with('192.0.2.7')
