"""Exercise installation boundaries without downloading or changing an environment."""

import contextlib
import importlib.metadata
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import bootstrap


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.env = self.root / '.venv'
        self.python = self.env / 'bin/python'
        self.requirements = self.root / 'requirements.txt'
        self.requirements.write_text('torch==2.10.0\ntorchvision==0.25.0\nfastapi==0.143.0\n')
        self.versions = {'torch': '2.10.0+cpu', 'torchvision': '0.25.0+cpu',
                         'fastapi': '0.143.0'}
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in [('ROOT', self.root), ('ENV', self.env),
                            ('PYTHON', self.python), ('REQUIREMENTS', self.requirements),
                            ('PENDING', self.env / '.jingwei-installing')]:
            self.stack.enter_context(patch.object(bootstrap, name, value))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(contextlib.redirect_stderr(io.StringIO()))

    def ready(self, versions=None, python_version=(3, 12), prefix=None):
        def version(name):
            try:
                return (self.versions if versions is None else versions)[name]
            except KeyError:
                raise importlib.metadata.PackageNotFoundError(name)

        with patch.object(bootstrap.sys, 'version_info', python_version), \
                patch.object(bootstrap.sys, 'prefix', str(prefix or self.env)), \
                patch.object(bootstrap.importlib.metadata, 'version', side_effect=version):
            return bootstrap.ready()

    def existing_environment(self, with_python=True):
        self.env.mkdir()
        if with_python:
            self.python.parent.mkdir()
            self.python.write_bytes(b'existing interpreter')
        (self.env / 'user-file').write_bytes(b'preserve existing environment')
        (self.root / 'runtime').mkdir()
        (self.root / 'runtime/settings.json').write_bytes(b'{"institution":"saved"}')
        (self.root / 'weights').mkdir()
        (self.root / 'weights/CFP.pth').write_bytes(b'preserve weights')

    def files(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob('*')
                if path.is_file() and path.name != '.jingwei-installing'}

    def test_ready_accepts_cpu_suffixes_and_requires_no_installer(self):
        with patch.object(bootstrap.subprocess, 'run') as run:
            self.assertTrue(self.ready())
            run.assert_not_called()

    def test_ready_rejects_wrong_python_or_environment(self):
        self.assertFalse(self.ready(python_version=(3, 13)))
        self.assertFalse(self.ready(prefix=self.root / 'other-environment'))

    def test_ready_rejects_missing_or_wrong_dependency(self):
        for versions in [dict(self.versions, torch='2.9.0+cpu'),
                         {name: value for name, value in self.versions.items() if name != 'fastapi'}]:
            with self.subTest(versions=versions):
                self.assertFalse(self.ready(versions))

    def test_unfinished_install_is_not_ready_despite_matching_versions(self):
        self.env.mkdir()
        (self.env / '.jingwei-installing').touch()
        self.assertFalse(self.ready())

    def test_incomplete_environment_is_preserved(self):
        self.existing_environment(with_python=False)
        before = self.files()
        with patch.object(bootstrap, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'Rename it'):
                bootstrap.install('uv')
            run.assert_not_called()
        self.assertEqual(self.files(), before)

    def test_wrong_python_environment_is_preserved(self):
        self.existing_environment()
        before = self.files()
        with patch.object(bootstrap.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 1)), \
                patch.object(bootstrap, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'Python 3.12'):
                bootstrap.install('uv')
            run.assert_not_called()
        self.assertEqual(self.files(), before)

    def test_missing_dependency_installs_into_existing_environment(self):
        self.existing_environment()
        before = self.files()
        missing = {name: value for name, value in self.versions.items() if name != 'fastapi'}
        self.assertFalse(self.ready(missing))
        with patch.object(bootstrap.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 0)), \
                patch.object(bootstrap, 'run') as run:
            bootstrap.install('uv')
        commands = [call.args for call in run.call_args_list]
        self.assertFalse(any(command[1] == 'venv' for command in commands))
        installers = [command for command in commands if command[1] == 'pip']
        self.assertTrue(installers)
        for command in installers:
            self.assertEqual(command[command.index('--python') + 1], self.python)
        self.assertEqual(self.files(), before)

    def test_new_environment_uses_selected_bootstrap_python(self):
        def create_environment(*command):
            if command[1] == 'venv':
                self.env.mkdir()

        with patch.object(bootstrap, 'run', side_effect=create_environment) as run:
            bootstrap.install('uv')
        run.assert_any_call('uv', 'venv', '--python', bootstrap.sys.executable, self.env)

    def test_install_failure_prevents_launch_and_can_retry(self):
        self.existing_environment()
        before = self.files()
        with patch.object(bootstrap.sys, 'argv', ['bootstrap.py', '--uv', 'uv']), \
                patch.object(bootstrap.subprocess, 'run',
                             return_value=subprocess.CompletedProcess([], 0)), \
                patch.object(bootstrap.subprocess, 'call', return_value=0) as launch, \
                patch.object(bootstrap, 'run',
                             side_effect=subprocess.CalledProcessError(1, ['uv', 'pip'])) as run:
            self.assertEqual(bootstrap.main(), 1)
            launch.assert_not_called()
            self.assertEqual(self.files(), before)
            self.assertTrue((self.env / '.jingwei-installing').is_file())
            self.assertFalse(self.ready())
            run.reset_mock()
            run.side_effect = None
            self.assertEqual(bootstrap.main(), 0)
            launch.assert_called_once()
            for call in run.call_args_list:
                if call.args[1] == 'pip':
                    self.assertIn('--reinstall', call.args)
            self.assertFalse((self.env / '.jingwei-installing').exists())
        self.assertEqual(self.files(), before)

    def test_import_verification_failure_prevents_launch(self):
        self.existing_environment()

        def fail_import(*command):
            if command[0] == self.python and command[1] == '-c':
                raise subprocess.CalledProcessError(1, list(map(str, command)))

        with patch.object(bootstrap.sys, 'argv', ['bootstrap.py', '--uv', 'uv']), \
                patch.object(bootstrap.subprocess, 'run',
                             return_value=subprocess.CompletedProcess([], 0)), \
                patch.object(bootstrap.subprocess, 'call') as launch, \
                patch.object(bootstrap, 'run', side_effect=fail_import):
            self.assertEqual(bootstrap.main(), 1)
            launch.assert_not_called()
            self.assertTrue((self.env / '.jingwei-installing').is_file())
            self.assertFalse(self.ready())

    def test_failed_final_readiness_check_restores_pending_marker(self):
        self.existing_environment()

        def fail_check(*command):
            if command[-1] == '--check':
                raise subprocess.CalledProcessError(1, list(map(str, command)))

        with patch.object(bootstrap.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 0)), \
                patch.object(bootstrap, 'run', side_effect=fail_check):
            with self.assertRaises(subprocess.CalledProcessError):
                bootstrap.install('uv')
        self.assertTrue((self.env / '.jingwei-installing').is_file())
        self.assertFalse(self.ready())

    def test_windows_and_linux_keep_cpu_backend_on_retries(self):
        self.existing_environment()
        for platform in ['win32', 'linux']:
            with self.subTest(platform=platform), \
                    patch.object(bootstrap.sys, 'platform', platform), \
                    patch.object(bootstrap.subprocess, 'run',
                                 return_value=subprocess.CompletedProcess([], 0)), \
                    patch.object(bootstrap, 'run') as run:
                (self.env / '.jingwei-installing').touch()
                bootstrap.install('uv')
                installers = [call.args for call in run.call_args_list if call.args[1] == 'pip']
                self.assertTrue(installers)
                for command in installers:
                    self.assertEqual(command[command.index('--torch-backend') + 1], 'cpu')
                    self.assertIn('--reinstall', command)

    def test_launch_arguments_and_exit_status_are_preserved(self):
        with patch.object(bootstrap.sys, 'argv',
                          ['bootstrap.py', '--uv', 'uv', '--port', '8877', '--no-browser']), \
                patch.object(bootstrap, 'install'), \
                patch.object(bootstrap.subprocess, 'call', return_value=17) as launch:
            self.assertEqual(bootstrap.main(), 17)
        launch.assert_called_once_with([str(self.python), str(self.root / 'launch.py'),
                                        '--port', '8877', '--no-browser'], cwd=self.root)


if __name__ == '__main__':
    unittest.main()
