"""Verify production network settings reach the server and deployment checks."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cmdb.constants.DCMDB import DCMDB
from cmdb.interface.Configuration import Configuration
from cmdb.interface.Network import Network
from cmdb.server.CmdbServer import main


ROOT = Path(__file__).resolve().parents[1]


class NetworkConfigurationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        base = patch.object(DCMDB, 'BASE_DIR', str(self.root))
        base.start()
        self.addCleanup(base.stop)
        self.addCleanup(Network._bindings.cache_clear)
        self.path = self.root / DCMDB.CONFIG_FILE
        self.path.parent.mkdir()

    def write(self, values):
        self.path.write_text(json.dumps(values))

    def read(self):
        return Configuration.read(self.path, DCMDB.CMDB_NETWORK)

    def test_install_creates_defaults_and_preserves_overrides(self):
        self.path.parent.rmdir()
        Configuration.install()
        self.assertEqual(json.loads(self.path.read_text()), {
            'network': {'http': {'interface': '0.0.0.0', 'port': 14444}}})
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o644)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o755)
        self.write({'network': {'http': {'interface': '127.0.0.2', 'port': 15000}}})
        original = self.path.read_bytes()
        Configuration.install()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(Network.binding('http'), ('127.0.0.2', 15000))

    def test_defaults_partial_overrides_and_restart_semantics(self):
        self.assertEqual(self.read(), {'http': ('0.0.0.0', 14444)})
        self.write({'network': {'http': {'port': 15000}}})
        self.assertEqual(Network.binding('http'), ('0.0.0.0', 15000))
        self.assertEqual(Network.destination('http'), ('127.0.0.1', 15000))
        self.write({'network': {'http': {'interface': '192.0.2.10'}}})
        self.assertEqual(Network.binding('http'), ('0.0.0.0', 15000))
        Network._bindings.cache_clear()  # A new process reloads the file.
        self.assertEqual(Network.destination('http'), ('192.0.2.10', 14444))
        with self.assertRaises(KeyError):
            Network.binding('missing')

    def test_invalid_configuration_identifies_field(self):
        cases = [([], 'network settings'), ({'netwrok': {}}, 'network settings'),
                 ({'network': []}, 'network must be an object'),
                 ({'network': {'typo': {}}}, 'network.typo'),
                 ({'network': {'http': []}}, 'network.http'),
                 ({'network': {'http': {'host': '127.0.0.1'}}}, 'network.http')]
        for interface in (None, 123, '', 'localhost', '999.0.0.1', '::1'):
            cases.append(({'network': {'http': {'interface': interface}}}, 'network.http.interface'))
        for port in (None, True, '1234', 0, -1, 65536, 1.5):
            cases.append(({'network': {'http': {'port': port}}}, 'network.http.port'))
        for values, field in cases:
            with self.subTest(values=values):
                self.write(values)
                with self.assertRaisesRegex(ValueError, field):
                    self.read()
        self.path.write_text('{bad json')
        with self.assertRaisesRegex(ValueError, 'invalid JSON'):
            Configuration.install()
        self.assertEqual(self.path.read_text(), '{bad json')

    def test_server_uses_inventory_configuration_and_explicit_arguments(self):
        database = {'DB_HOST': 'localhost', 'DB_PORT': '3306', 'DB_NAME': 'cmdb',
                    'DB_USER': 'cmdb', 'DB_PASSWORD': 'test'}
        with patch.object(DCMDB, 'CMDB_NETWORK', (('http', '192.0.2.10', 15000),)):
            for config, arguments, expected in (
                ({}, [], ('192.0.2.10', 15000)),
                ({'network': {'http': {'port': 15001}}}, [], ('192.0.2.10', 15001)),
                ({}, ['--host', '127.0.0.3', '--port', '15002'], ('127.0.0.3', 15002)),
            ):
                with self.subTest(arguments=arguments, config=config):
                    Network._bindings.cache_clear()
                    self.write(config)
                    with patch('sys.argv', ['cmdb-server', *arguments]), patch.dict('os.environ', database):
                        with patch('cmdb.server.CmdbServer.CmdbHTTPServer') as server:
                            server.return_value.__enter__.return_value.serve_forever.side_effect = KeyboardInterrupt
                            with patch('cmdb.server.CmdbServer.signal.signal'), redirect_stdout(io.StringIO()):
                                with patch('cmdb.server.CmdbServer.InventoryCoordinator'), patch('cmdb.server.CmdbServer.BackupManager'):
                                    main()
                            self.assertEqual(server.call_args.args[0], expected)

    def test_installer_health_checks_follow_configured_destination(self):
        script = (ROOT / 'scripts/install-services.sh').read_text()
        source = script.rsplit("python3 -B - <<'PY'\n", 1)[1].split('\nPY', 1)[0]
        for interface, host in (('0.0.0.0', '127.0.0.1'), ('192.0.2.10', '192.0.2.10')):
            with self.subTest(interface=interface):
                Network._bindings.cache_clear()
                self.write({'network': {'http': {'interface': interface, 'port': 15000}}})
                with patch('urllib.request.build_opener') as build, redirect_stdout(io.StringIO()):
                    response = build.return_value.open.return_value.__enter__.return_value
                    response.status = 200
                    with patch('json.load', side_effect=[{'status': status, 'service': 'cmdb-server'}
                                                        for status in ('ok', 'ready')]):
                        exec(compile(source, 'install-services.sh', 'exec'), {})
                    self.assertEqual([call.args[0] for call in build.return_value.open.call_args_list],
                                     [f'http://{host}:15000/{endpoint}' for endpoint in ('health', 'ready')])

    def test_restart_validates_before_touching_service(self):
        script = (ROOT / 'scripts/restart.sh').read_text()
        source = script.split(".venv/bin/python -B - <<'PY'\n", 1)[1].split('\nPY', 1)[0]
        with patch('subprocess.run') as run, redirect_stdout(io.StringIO()):
            self.write({'network': {'http': {'port': 15000}}})
            exec(compile(source, 'restart.sh', 'exec'), {})
            run.assert_called_once_with(['systemctl', 'restart', DCMDB.SERVICE_UNIT], check=True)
            run.reset_mock()
            self.path.write_text('{invalid')
            with self.assertRaises(ValueError):
                exec(compile(source, 'restart.sh', 'exec'), {})
            run.assert_not_called()
