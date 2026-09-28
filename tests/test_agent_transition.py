"""Account transition checks without modifying real accounts or contacting hosts."""

import importlib.util
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch


def load_script(name):
    path = Path(__file__).resolve().parents[1] / 'scripts' / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentTransitionTests(TestCase):
    def test_cleanup_skips_local_and_continues_after_failure(self):
        script = load_script('cleanup-remote-cmdb')
        with patch.object(script, 'SSH') as factory, patch('builtins.print'):
            ssh = factory.return_value
            ssh.is_local.side_effect = [True, False, False]
            ssh.run.side_effect = [subprocess.CalledProcessError(1, ['ssh'], stderr='denied'),
                                   SimpleNamespace(stdout='Removed cmdb account and home')]
            self.assertEqual(script.cleanup(['local', 'first', 'second', 'second'], 'local-id'), 1)
            self.assertEqual([call.args[0] for call in ssh.run.call_args_list], ['first', 'second'])
            for call in ssh.run.call_args_list:
                self.assertEqual(call.kwargs['user'], 'root')
                self.assertIn('userdel --remove cmdb', call.kwargs['input'])
                self.assertEqual(call.args[1], 'sh -s -- local-id')

    def test_remote_script_refuses_local_machine_even_through_an_alias(self):
        script = load_script('cleanup-remote-cmdb')
        identity = Path('/etc/machine-id').read_text().strip()
        # The real script exits before getent/userdel. Mock only id so this check
        # also exercises the guard when the tests run as an unprivileged user.
        source = script.REMOVE_ACCOUNT.replace('[ "$(id -u)" = 0 ]', ':')
        result = subprocess.run(['/bin/sh', '-s', '--', identity], input=source,
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Refusing to remove the local service account', result.stderr)

    def test_local_installer_creates_agent_then_reuses_it(self):
        script = load_script('install-agent')
        with patch.object(script.os, 'geteuid', return_value=0), \
                patch.object(script.pwd, 'getpwnam', side_effect=[KeyError(), object()]), \
                patch.object(script.Path, 'read_text', return_value='ssh-ed25519 TEST cmdb\n'), \
                patch.object(script.subprocess, 'run') as run:
            script.main()
            script.main()
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(sum(command[0] == 'useradd' for command in commands), 1)
            self.assertEqual(commands[0][-1], 'cmdbagent')
            self.assertIn('/var/lib/cmdbagent', commands[0])
            self.assertEqual(commands[1][-2:], ['cmdbagent', 'ssh-ed25519 TEST cmdb'])
            self.assertEqual(commands[1], commands[4])
            self.assertEqual(commands[2][0], "mariadb")
            self.assertEqual(commands[3][:3], ["runuser", "-u", "cmdbagent"])
            for command in (commands[2], commands[3]):
                self.assertIn('--protocol=socket', command)
                self.assertIn('--skip-ssl', command)
