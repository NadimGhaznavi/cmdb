"""Exercise releases against disposable repositories and a local bare remote."""

import ast
import errno
import os
from pathlib import Path
import pty
import select
import shutil
import subprocess
import tempfile
import time
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/new-release.sh'


class NewReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='cmdb-release-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.repo = root / 'project'
        self.repo.mkdir()
        self.remote = root / 'remote.git'
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1',
                        GIT_CONFIG_GLOBAL='/dev/null', TERM='xterm')
        self.env.pop('NO_COLOR', None)
        self.env.pop('GIT_DIR', None)
        self.env.pop('GIT_WORK_TREE', None)
        self.git('init', '--bare', str(self.remote))
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Release Test')
        self.git('config', 'user.email', 'release@example.invalid')
        (self.repo / 'scripts').mkdir()
        shutil.copy2(SCRIPT, self.repo / 'scripts/new-release.sh')
        self.constants = self.repo / 'cmdb/constants/DCMDB.py'
        self.constants.parent.mkdir(parents=True)
        self.constants.write_text(
            'from typing import Final\n\nclass DCMDB:\n'
            '    VERSION: Final[str] = "1.0.0"  # version\n'
            '    CMDB_CODENAME: Final[str] = "Old"  # codename\n'
            '    OTHER = "Keep this"\n')
        (self.repo / 'CHANGELOG.md').write_text(
            '## [Unreleased]\n\n- Pending change.\n\n## [1.0.0] - earlier\n')
        self.commit()
        self.git('branch', 'dev')
        self.git('remote', 'add', 'origin', str(self.remote))
        self.git('push', 'origin', 'main', 'dev')
        self.git('switch', '-c', 'feat/maint-1.0.1')
        (self.repo / 'feature.txt').write_text('Feature change\n')
        self.commit()
        self.initial_head = self.git('rev-parse', 'HEAD')
        self.initial_remote = self.git('ls-remote', 'origin')

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.repo, env=self.env,
                              check=True, text=True, capture_output=True).stdout.strip()

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-m', 'Test fixture')

    def run_release(self, version='1.0.1', message='New release', next_branch=None,
                    reply='y', terminal=True, no_color=False):
        command = ['bash', 'scripts/new-release.sh', version, message]
        if next_branch is not None:
            command.append(next_branch)
        env = self.env.copy()
        if no_color:
            env['NO_COLOR'] = ''
        if not terminal:
            result = subprocess.run(command, cwd=self.repo, env=env, input='y\n',
                                    capture_output=True, text=True, timeout=20)
            return result.returncode, result.stdout + result.stderr
        master, slave = pty.openpty()
        process = subprocess.Popen(command, cwd=self.repo, env=env,
                                   stdin=slave, stdout=slave, stderr=slave)
        os.close(slave)
        output = bytearray()
        answered = False
        deadline = time.monotonic() + 20
        try:
            while True:
                if time.monotonic() > deadline:
                    self.fail('Release script timed out: ' + output.decode(errors='replace'))
                ready, _, _ = select.select([master], [], [], 0.1)
                if not ready:
                    continue
                try:
                    chunk = os.read(master, 65536)
                except OSError as error:
                    if error.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    break
                output.extend(chunk)
                if not answered and b'Create and push this release? [y/N]' in output:
                    os.write(master, (reply + '\n').encode())
                    answered = True
            process.wait(timeout=5)
            return process.returncode, output.decode()
        finally:
            os.close(master)
            if process.poll() is None:
                process.kill()
            process.wait()

    def assert_unreleased(self):
        self.assertEqual(self.git('branch', '--show-current'), 'feat/maint-1.0.1')
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.initial_head)
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertEqual(self.git('tag'), '')
        self.assertEqual(self.git('ls-remote', 'origin'), self.initial_remote)

    def test_release_updates_literals_and_publishes_all_refs(self):
        message = 'A "quoted" café / & \\ path $(touch NEVER) `literal`\nSecond line'
        code, output = self.run_release(version='1.0.1-rc.1+build.2', message=message, reply='Y')
        self.assertEqual(code, 0, output)
        values = {node.target.id: node.value.value for node in ast.walk(
            ast.parse(self.constants.read_text())) if isinstance(node, ast.AnnAssign)}
        self.assertEqual(values['VERSION'], '1.0.1-rc.1+build.2')
        self.assertEqual(values['CMDB_CODENAME'], message)
        self.assertIn('# codename', self.constants.read_text())
        self.assertIn('OTHER = "Keep this"', self.constants.read_text())
        self.assertFalse((self.repo / 'NEVER').exists())
        self.assertEqual(self.git('branch', '--show-current'), 'feat/maint-1.0.2')
        self.assertEqual(self.git('rev-parse', 'main'), self.git('rev-parse', 'dev'))
        self.assertEqual(self.git('rev-parse', 'main'),
                         self.git('rev-parse', 'v1.0.1-rc.1+build.2^{}'))
        self.assertEqual(self.git('cat-file', '-t', 'v1.0.1-rc.1+build.2'), 'tag')
        refs = self.git('ls-remote', 'origin')
        for ref in ('refs/heads/main', 'refs/heads/dev', 'refs/tags/v1.0.1-rc.1+build.2'):
            self.assertIn(ref, refs)
        self.assertNotIn('refs/heads/feat/maint-1.0.2', refs)
        self.assertIn('## [1.0.1-rc.1+build.2] - ', (self.repo / 'CHANGELOG.md').read_text())
        self.assertIn('[ \x1b[32mPASSED\x1b[0m ]', output)
        self.assertIn('Release 1.0.1-rc.1+build.2: ' + message,
                      self.git('log', '-1', '--format=%B', 'main'))

    def test_declining_confirmation_changes_no_release_state(self):
        for reply in ('', 'n', 'yes'):
            with self.subTest(reply=reply):
                code, output = self.run_release(reply=reply, no_color=True)
                self.assertEqual(code, 0, output)
                self.assertIn('[ WARNING ] Release cancelled.', output)
                self.assertNotIn('\x1b[', output)
                self.assert_unreleased()

    def test_noninteractive_input_cannot_confirm(self):
        code, output = self.run_release(terminal=False)
        self.assertNotEqual(code, 0)
        self.assertIn('[ FAIL ] Confirmation requires an interactive terminal.', output)
        self.assertNotIn('\x1b[', output)
        self.assert_unreleased()

    def test_invalid_versions_and_empty_messages_are_rejected(self):
        for version, message in [('v1.0.1', 'Release'), ('01.0.1', 'Release'),
                                 ('1.0.1-01', 'Release'), ('1.0.1', '  ')]:
            with self.subTest(version=version, message=message):
                code, output = self.run_release(version=version, message=message)
                self.assertNotEqual(code, 0)
                self.assertIn('FAIL', output)
                self.assertNotIn('Create and push', output)
                self.assert_unreleased()

    def test_missing_codename_stops_before_confirmation(self):
        self.constants.write_text(self.constants.read_text().replace('CMDB_CODENAME', 'OLD_NAME'))
        self.commit()
        self.initial_head = self.git('rev-parse', 'HEAD')
        code, output = self.run_release()
        self.assertNotEqual(code, 0)
        self.assertIn('exactly one CMDB_CODENAME assignment', output)
        self.assertNotIn('Create and push', output)
        self.assert_unreleased()

    def test_existing_tag_is_rejected(self):
        self.git('tag', 'v1.0.1')
        code, output = self.run_release()
        self.assertNotEqual(code, 0)
        self.assertIn('Tag v1.0.1 already exists.', output)
        self.assertNotIn('Create and push', output)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.initial_head)
        self.assertEqual(self.git('ls-remote', 'origin'), self.initial_remote)

    def test_failed_push_reports_step_and_leaves_remote_unchanged(self):
        hook = self.remote / 'hooks/pre-receive'
        hook.write_text('#!/bin/sh\nexit 1\n')
        hook.chmod(0o755)
        code, output = self.run_release(no_color=True)
        self.assertNotEqual(code, 0)
        self.assertIn('[ FAIL ] Stopped during Push release refs atomically', output)
        self.assertNotIn('[ PASSED ] Push release refs atomically', output)
        self.assertEqual(self.git('ls-remote', 'origin'), self.initial_remote)
        self.assertEqual(self.git('branch', '--show-current'), 'dev')
        self.assertEqual(self.git('tag'), 'v1.0.1')

    def test_project_settings_and_explicit_next_branch_can_be_adapted(self):
        script = self.repo / 'scripts/new-release.sh'
        text = script.read_text()
        settings = {'project_name="CMDB"': 'project_name="Example"',
                    'cmdb/constants/DCMDB.py': 'example/constants.py',
                    'version_constant="VERSION"': 'version_constant="APP_VERSION"',
                    'codename_constant="CMDB_CODENAME"': 'codename_constant="APP_CODENAME"',
                    'changelog_file="CHANGELOG.md"': 'changelog_file="HISTORY.md"',
                    'remote="origin"': 'remote="upstream"',
                    'dev_branch="dev"': 'dev_branch="develop"',
                    'main_branch="main"': 'main_branch="stable"',
                    'feature_prefix="feat/maint-"': 'feature_prefix="feature/next-"'}
        for old, new in settings.items():
            text = text.replace(old, new)
        script.write_text(text)
        target = self.repo / 'example/constants.py'
        target.parent.mkdir()
        target.write_text('APP_VERSION = "1.0.0"\nAPP_CODENAME = "Old"\n')
        self.constants.unlink()
        (self.repo / 'CHANGELOG.md').rename(self.repo / 'HISTORY.md')
        self.git('branch', '-m', 'dev', 'develop')
        self.git('branch', '-m', 'main', 'stable')
        self.git('remote', 'rename', 'origin', 'upstream')
        self.git('push', 'upstream', 'stable', 'develop')
        self.commit()
        code, output = self.run_release(next_branch='feature/custom', no_color=True)
        self.assertEqual(code, 0, output)
        self.assertIn('APP_VERSION = "1.0.1"', target.read_text())
        self.assertIn('APP_CODENAME = "New release"', target.read_text())
        self.assertIn('Example release v1.0.1 published successfully.', output)
        self.assertEqual(self.git('branch', '--show-current'), 'feature/custom')
        self.assertEqual(self.git('rev-parse', 'stable'), self.git('rev-parse', 'develop'))
        self.assertIn('## [1.0.1] - ', (self.repo / 'HISTORY.md').read_text())
