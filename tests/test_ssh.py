"""SSH invocation and local key provisioning, without contacting remote hosts."""

from contextlib import ExitStack
from hashlib import sha256
import os
from pathlib import Path
import stat
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cmdb.constants.DCMDB import DCMDB
from cmdb.interface.SSH import SSH


class SSHTests(unittest.TestCase):
    def test_uptime_uses_inventory_command_and_validates_response(self):
        with patch.object(SSH, 'run') as run:
            run.return_value.stdout = '90061.25 120000.50\n'
            self.assertEqual(SSH().uptime('192.0.2.1'), 90061)
            run.assert_called_once_with('192.0.2.1', 'cat /proc/uptime', timeout=10, connect_timeout=5)
            for value in ('', '-1 0', 'nan 0', 'not uptime'):
                run.return_value.stdout = value
                with self.assertRaises(ValueError):
                    SSH().uptime('192.0.2.1')

    def setUp(self):
        local = patch('cmdb.interface.SSH.SSH.is_local', return_value=False)
        self.local = local.start()
        self.addCleanup(local.stop)

    @patch('cmdb.interface.SSH.subprocess.run')
    def test_local_command_bypasses_ssh_and_preserves_input_and_timeout(self, run):
        self.local.return_value = True
        import pwd
        SSH().run('127.0.0.1', 'sh -s', user=pwd.getpwuid(os.geteuid()).pw_name,
                  input='printf hello', timeout=7)
        self.assertEqual(run.call_args.args[0], ['/bin/sh', '-c', 'sh -s'])
        self.assertEqual(run.call_args.kwargs['input'], 'printf hello')
        self.assertEqual(run.call_args.kwargs['timeout'], 7)

    @patch('cmdb.interface.SSH.pwd.getpwnam')
    @patch('cmdb.interface.SSH.subprocess.run')
    def test_local_inventory_runs_as_agent_without_ssh(self, run, account):
        self.local.return_value = True
        account.return_value.pw_uid = os.geteuid() + 1
        SSH().run('127.0.0.1', 'hostname', input='example')
        self.assertEqual(run.call_args.args[0],
                         ['/usr/bin/sudo', '-n', '-H', '-u', 'cmdbagent', '--', '/bin/sh', '-c', 'hostname'])
        self.assertEqual(run.call_args.kwargs['input'], 'example')

    @patch('cmdb.interface.SSH.pwd.getpwnam')
    @patch('cmdb.interface.SSH.subprocess.run')
    def test_local_command_does_not_silently_use_a_different_identity(self, run, account):
        self.local.return_value = True
        account.return_value.pw_uid = os.geteuid() + 1
        with self.assertRaises(PermissionError):
            SSH().run('127.0.0.1', 'true', user='root')
        run.assert_not_called()

    @patch('cmdb.interface.SSH.subprocess.run')
    def test_remote_script_is_sent_on_stdin(self, run):
        script = 'printf hello\n'
        SSH().run('server', 'sh -s', user='root', input=script)
        self.assertEqual(run.call_args.kwargs['input'], script)
        self.assertNotIn('stdin', run.call_args.kwargs)

    @patch('cmdb.interface.SSH.subprocess.run')
    def test_remote_identity_and_output(self, run):
        command = "printf '%s' 'hello; world'"
        result = subprocess.CompletedProcess([], 0, 'hello; world', '')
        run.return_value = result
        self.assertIs(SSH().run('192.168.0.7', command, port=2222, timeout=60), result)
        args, options = run.call_args
        argv = args[0]
        self.assertEqual(argv[-3:], ['--', '192.168.0.7', command])
        self.assertEqual(argv[argv.index('-l') + 1], 'cmdbagent')
        self.assertEqual(argv[argv.index('-i') + 1], DCMDB.SSH_KEY)
        self.assertEqual(argv[argv.index('-p') + 1], '2222')
        self.assertIn('BatchMode=yes', argv)
        self.assertIn('StrictHostKeyChecking=accept-new', argv)
        self.assertIn(f'UserKnownHostsFile={DCMDB.SSH_KNOWN_HOSTS}', argv)
        self.assertEqual(options['timeout'], 60)
        self.assertTrue(options['check'])
        self.assertNotIn('shell', options)

    @patch('cmdb.interface.SSH.subprocess.run')
    def test_root_login_uses_same_local_identity_without_sudo(self, run):
        SSH().run('192.168.0.7', 'id -u', user='root')
        argv = run.call_args.args[0]
        self.assertEqual(argv[0], '/usr/bin/ssh')
        self.assertEqual(argv[argv.index('-l') + 1], 'root')
        self.assertEqual(argv[argv.index('-i') + 1], DCMDB.SSH_KEY)
        self.assertIn(f'UserKnownHostsFile={DCMDB.SSH_KNOWN_HOSTS}', argv)
        self.assertEqual(argv[-3:], ['--', '192.168.0.7', 'id -u'])

    @patch('cmdb.interface.SSH.subprocess.run')
    def test_invalid_target_or_options_do_not_launch_ssh(self, run):
        for host in ('', '-oProxyCommand=anything', 'root@server', 'server name', 'host\0'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                SSH().run(host, 'true')
        for options in ({'port': 0}, {'port': 65536}, {'timeout': 0}, {'connect_timeout': -1}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                SSH().run('server', 'true', **options)
        with self.assertRaises(ValueError):
            SSH().run('server', ' ')
        for user in ('', '-root', 'root@server', 'root user', 'root\0'):
            with self.subTest(user=user), self.assertRaises(ValueError):
                SSH().run('server', 'true', user=user)
        run.assert_not_called()

    @patch('cmdb.interface.SSH.subprocess.run')
    def test_failures_propagate_with_output(self, run):
        for error in (subprocess.CalledProcessError(255, ['ssh'], stderr='Permission denied'),
                      subprocess.TimeoutExpired(['ssh'], 30), FileNotFoundError('ssh')):
            run.side_effect = error
            with self.subTest(error=error), self.assertRaises(type(error)) as caught:
                SSH().run('server', 'uname -a')
            self.assertIs(caught.exception, error)


@unittest.skipUnless(Path('/usr/bin/ssh-keygen').is_file(), 'OpenSSH client required')
class SSHKeyTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = self.stack.enter_context(TemporaryDirectory(prefix='cmdb-ssh-test-'))
        self.home = Path(directory) / 'cmdb'
        self.ssh = self.home / '.ssh'
        self.key = self.ssh / 'id_ed25519'
        self.public = self.ssh / 'id_ed25519.pub'
        self.known = self.ssh / 'known_hosts'
        for attribute, value in {'SERVICE_HOME': self.home, 'SSH_DIR': self.ssh,
                                 'SSH_KEY': self.key, 'SSH_KNOWN_HOSTS': self.known}.items():
            self.stack.enter_context(patch.object(DCMDB, attribute, str(value)))
        self.stack.enter_context(patch('pwd.getpwnam', return_value=SimpleNamespace(
            pw_uid=os.getuid(), pw_gid=os.getgid())))
        self.stack.enter_context(patch('builtins.print'))
        script = Path(__file__).resolve().parents[1] / 'scripts/install-ssh.sh'
        self.source = script.read_text().split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]

    def provision(self):
        exec(compile(self.source, 'scripts/install-ssh.sh', 'exec'), {})

    def test_provisioning_generates_valid_key_with_account_ownership_and_modes(self):
        self.provision()
        self.assertTrue(self.public.read_text().startswith('ssh-ed25519 '))
        derived = subprocess.run(['/usr/bin/ssh-keygen', '-y', '-P', '', '-f', str(self.key)],
                                 capture_output=True, text=True, check=True).stdout
        self.assertEqual(derived, self.public.read_text())
        for path, mode in ((self.home, 0o750), (self.ssh, 0o700), (self.key, 0o600),
                           (self.public, 0o644), (self.known, 0o600)):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
            self.assertEqual(path.stat().st_uid, os.getuid())
            self.assertEqual(path.stat().st_gid, os.getgid())

    def test_reinstall_retains_identity_and_known_hosts_and_recovers_public_key(self):
        self.provision()
        original = sha256(self.key.read_bytes()).digest()
        public = self.public.read_text()
        self.known.write_text('retained known host\n')
        self.public.unlink()
        self.provision()
        self.provision()
        self.assertEqual(sha256(self.key.read_bytes()).digest(), original)
        self.assertEqual(self.public.read_text(), public)
        self.assertEqual(self.known.read_text(), 'retained known host\n')

    def test_invalid_existing_key_is_not_replaced(self):
        self.ssh.mkdir(parents=True)
        self.key.write_text('invalid existing key')
        with self.assertRaises(subprocess.CalledProcessError):
            self.provision()
        self.assertEqual(self.key.read_text(), 'invalid existing key')
