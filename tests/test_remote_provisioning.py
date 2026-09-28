"""Run the provisioning shell with account commands replaced by temporary fixtures."""

import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from unittest import TestCase


STUB = '''#!/usr/bin/python3
import json, os, pathlib, sys
state_file = pathlib.Path(os.environ['CMDB_ACCOUNT_FIXTURE'])
state = json.loads(state_file.read_text())
command = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
if command == 'id':
    print(0 if len(args) == 1 else (os.getuid() if args[0] == '-u' else os.getgid()))
elif command == 'getent':
    if not state['exists']:
        sys.exit(2)
    if args[0] == 'passwd':
        print(f"cmdb:x:{os.getuid()}:{os.getgid()}::{state['home']}:{state['shell']}")
    elif args[0] == 'shadow':
        print('cmdb:' + state['password'] + ':0:0:99999:7:::')
elif command == 'useradd':
    state['exists'] = True
    state['shell'] = args[args.index('--shell') + 1]
    state['password'] = args[args.index('--password') + 1]
    state['creates'] += 1
elif command == 'usermod':
    key = {'--shell': 'shell', '--password': 'password', '--home': 'home'}[args[0]]
    state[key] = args[1]
elif command != 'chown':
    sys.exit(1)
state_file.write_text(json.dumps(state))
'''


class RemoteProvisioningTests(TestCase):
    def setUp(self):
        temp = TemporaryDirectory(prefix='cmdb-remote-fixture-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / 'home'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for command in ('id', 'getent', 'useradd', 'usermod', 'chown'):
            executable = self.bin / command
            executable.write_text(STUB)
            executable.chmod(0o755)
        self.state = self.root / 'state.json'
        self.state.write_text(json.dumps({'exists': False, 'home': str(self.home),
                                         'shell': '/bin/sh', 'password': '!', 'creates': 0}))
        self.script = Path(__file__).resolve().parents[1] / 'cmdb/activity/scripts/provision-cmdb.sh'
        self.key = 'ssh-ed25519 AAAATEST cmdb'

    def provision(self):
        return subprocess.run(['/bin/sh', str(self.script), 'cmdb', self.key],
                              env={**os.environ, 'PATH': str(self.bin) + ':/usr/bin:/bin',
                                   'CMDB_ACCOUNT_FIXTURE': str(self.state)},
                              capture_output=True, text=True, check=True)

    def test_create_and_repeat_preserve_other_keys_and_do_not_duplicate_ours(self):
        self.provision()
        authorized = self.home / '.ssh/authorized_keys'
        authorized.write_text(authorized.read_text() + 'ssh-ed25519 OTHER existing\n')
        self.provision()
        self.provision()
        self.assertEqual(authorized.read_text().splitlines().count(self.key), 1)
        self.assertIn('ssh-ed25519 OTHER existing', authorized.read_text())
        self.assertEqual(authorized.stat().st_mode & 0o777, 0o600)
        self.assertEqual(authorized.parent.stat().st_mode & 0o777, 0o700)
        state = json.loads(self.state.read_text())
        self.assertEqual(state['creates'], 1)
        self.assertEqual(state['password'], '*NP*')

    def test_existing_service_account_gets_login_shell_and_key_without_recreation(self):
        state = json.loads(self.state.read_text())
        state.update(exists=True, shell='/usr/sbin/nologin', password='!')
        self.state.write_text(json.dumps(state))
        self.provision()
        state = json.loads(self.state.read_text())
        self.assertEqual(state['creates'], 0)
        self.assertEqual(state['shell'], '/bin/sh')
        self.assertEqual(state['password'], '*NP*')

    def test_existing_password_and_shell_are_preserved(self):
        state = json.loads(self.state.read_text())
        state.update(exists=True, shell='/bin/bash', password='existing-password-hash')
        self.state.write_text(json.dumps(state))
        self.provision()
        state = json.loads(self.state.read_text())
        self.assertEqual(state['shell'], '/bin/bash')
        self.assertEqual(state['password'], 'existing-password-hash')

    def test_authorized_keys_symlink_is_not_followed(self):
        self.home.mkdir()
        (self.home / '.ssh').mkdir()
        unrelated = self.root / 'unrelated'
        unrelated.write_text('unchanged')
        (self.home / '.ssh/authorized_keys').symlink_to(unrelated)
        with self.assertRaises(subprocess.CalledProcessError):
            self.provision()
        self.assertEqual(unrelated.read_text(), 'unchanged')
