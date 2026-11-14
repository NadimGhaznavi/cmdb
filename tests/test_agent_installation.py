"""FreeIPA agent installation checks without modifying real accounts."""

import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


def load_script(name):
    path = Path(__file__).resolve().parents[1] / 'scripts' / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentInstallationTests(TestCase):
    def test_local_installer_reuses_directory_identity_and_provisions_only_mariadb(self):
        script = load_script('install-agent')
        with patch.object(script.os, 'geteuid', return_value=0), \
                patch.object(script.pwd, 'getpwnam', return_value=object()), \
                patch.object(script.Path, 'read_text', return_value='root:x:0:0::/root:/bin/sh\n'), \
                patch.object(script, 'provisioning_sql', return_value='agent grants'), \
                patch.object(script.subprocess, 'run') as run:
            script.main()
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(len(commands), 2)
            self.assertEqual(commands[0][0], 'mariadb')
            self.assertEqual(commands[1][:3], ['runuser', '-u', 'cmdbagent'])
            self.assertEqual(run.call_args_list[0].kwargs['input'], 'agent grants')
            for command in commands:
                self.assertIn('--protocol=socket', command)
                self.assertIn('--skip-ssl', command)

    def test_missing_directory_identity_does_not_create_a_local_account(self):
        script = load_script('install-agent')
        with patch.object(script.os, 'geteuid', return_value=0), \
                patch.object(script.Path, 'read_text', return_value=''), \
                patch.object(script.pwd, 'getpwnam', side_effect=KeyError()), \
                patch.object(script.subprocess, 'run') as run:
            with self.assertRaisesRegex(SystemExit, 'FreeIPA cmdbagent must resolve'):
                script.main()
            run.assert_not_called()

    def test_local_account_cannot_mask_the_directory_identity(self):
        script = load_script('install-agent')
        with patch.object(script.os, 'geteuid', return_value=0), \
                patch.object(script.Path, 'read_text', return_value='cmdbagent:x:123:123::/home/cmdbagent:/bin/sh\n'), \
                patch.object(script.subprocess, 'run') as run:
            with self.assertRaisesRegex(SystemExit, 'Remove the local cmdbagent account'):
                script.main()
            run.assert_not_called()
