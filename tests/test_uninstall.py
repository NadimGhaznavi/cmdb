"""Verify uninstall ordering and retained resources without touching the host."""

from contextlib import ExitStack
from pathlib import Path
import subprocess
import unittest
from unittest.mock import call, patch

from cmdb.constants.DCmdb import DCmdb


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/uninstall.sh'
SOURCE = SCRIPT.read_text().split("<<'PYTHON'\n", 1)[1].rsplit('\nPYTHON', 1)[0]


class UninstallTests(unittest.TestCase):
    def run_uninstall(self, *, installed=True, failure=None):
        events = []

        def run(command, **kwargs):
            events.append((command, kwargs.get('input')))
            if failure and failure in kwargs.get('input', ''):
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0, stdout='loaded' if installed else 'not-found')

        with ExitStack() as stack:
            stack.enter_context(patch('subprocess.run', side_effect=run))
            stack.enter_context(patch('pathlib.Path.is_symlink', return_value=False))
            stack.enter_context(patch('pathlib.Path.exists', return_value=installed))
            unlink = stack.enter_context(patch('pathlib.Path.unlink', autospec=True))
            remove = stack.enter_context(patch('shutil.rmtree'))
            stack.enter_context(patch('builtins.print'))
            if failure:
                with self.assertRaises(subprocess.CalledProcessError):
                    exec(compile(SOURCE, str(SCRIPT), 'exec'), {})
            else:
                exec(compile(SOURCE, str(SCRIPT), 'exec'), {})
        return events, unlink, remove

    def test_uninstall_drops_database_and_retains_credentials_and_accounts(self):
        events, unlink, remove = self.run_uninstall()
        self.assertEqual(events, [
            (['mariadb', '--protocol=socket', '--user=root'], 'SELECT 1;\n'),
            (['systemctl', 'show', DCmdb.SERVICE_UNIT, '--property=LoadState', '--value'], None),
            (['systemctl', 'disable', '--now', DCmdb.SERVICE_UNIT], None),
            (['mariadb', '--protocol=socket', '--user=root'], 'DROP DATABASE IF EXISTS `cmdb`;\n'),
            (['systemctl', 'daemon-reload'], None),
        ])
        self.assertEqual(unlink.call_args_list, [
            call(Path('/etc/systemd/system/cmdb-server.service'), missing_ok=True),
            call(Path('/etc/sudoers.d/cmdb-nmap'), missing_ok=True),
        ])
        remove.assert_called_once_with(Path('/opt/prod/cmdb'))

    def test_repeat_uninstall_handles_missing_deployment(self):
        events, _, remove = self.run_uninstall(installed=False)
        self.assertFalse(any('disable' in command for command, _ in events))
        self.assertTrue(any(sql == 'DROP DATABASE IF EXISTS `cmdb`;\n' for _, sql in events))
        remove.assert_not_called()

    def test_database_access_failure_leaves_deployment_untouched(self):
        events, unlink, remove = self.run_uninstall(failure='SELECT')
        self.assertEqual(len(events), 1)
        unlink.assert_not_called()
        remove.assert_not_called()

    def test_drop_failure_preserves_files_for_retry(self):
        events, unlink, remove = self.run_uninstall(failure='DROP')
        self.assertIn((['systemctl', 'disable', '--now', DCmdb.SERVICE_UNIT], None), events)
        unlink.assert_not_called()
        remove.assert_not_called()

    def test_unexpected_application_path_is_rejected_before_commands(self):
        with patch.object(DCmdb, 'BASE_DIR', '/opt/prod'), patch('subprocess.run') as run:
            with self.assertRaises(SystemExit):
                exec(compile(SOURCE, str(SCRIPT), 'exec'), {})
        run.assert_not_called()
