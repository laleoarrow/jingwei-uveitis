"""Verify local setup, interrupted installs, and existing-environment reuse."""
import contextlib
import importlib.metadata
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import bootstrap


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.env = self.root / ".venv"
        self.python = self.env / "bin/python"
        self.pending = self.env / ".cfp-crop-installing"
        requirements = self.root / "requirements.txt"
        requirements.write_text("Pillow==11.3.0\n")
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        for name, value in (("ROOT", self.root), ("ENV", self.env), ("PYTHON", self.python),
                            ("PENDING", self.pending), ("REQUIREMENTS", requirements)):
            stack.enter_context(patch.object(bootstrap, name, value))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        stack.enter_context(contextlib.redirect_stderr(io.StringIO()))

    def ready(self, version=(3, 12), prefix=None, pillow="11.3.0"):
        with patch.object(bootstrap.sys, "version_info", version), \
                patch.object(bootstrap.sys, "prefix", str(prefix or self.env)), \
                patch.object(bootstrap.importlib.metadata, "version", return_value=pillow):
            return bootstrap.ready()

    def existing(self):
        self.python.parent.mkdir(parents=True)
        self.python.write_bytes(b"existing interpreter")
        self.marker = self.env / "keep.txt"
        self.marker.write_text("keep this environment")

    def test_ready_needs_local_supported_python_and_matching_dependencies(self):
        self.assertTrue(self.ready())
        self.assertTrue(self.ready(version=(3, 13)))
        self.assertFalse(self.ready(version=(3, 14)))
        self.assertFalse(self.ready(prefix=self.root / "other"))
        self.assertFalse(self.ready(pillow="10.0.0"))
        with patch.object(bootstrap.importlib.metadata, "version",
                          side_effect=importlib.metadata.PackageNotFoundError("Pillow")), \
                patch.object(bootstrap.sys, "prefix", str(self.env)):
            self.assertFalse(bootstrap.ready())
        self.env.mkdir()
        self.pending.touch()
        self.assertFalse(self.ready())

    def test_incomplete_environment_is_preserved(self):
        self.env.mkdir()
        marker = self.env / "keep.txt"
        marker.write_text("keep")
        with patch.object(bootstrap, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                bootstrap.install("uv")
            run.assert_not_called()
        self.assertEqual(marker.read_text(), "keep")

    def test_unsupported_environment_is_preserved(self):
        self.existing()
        with patch.object(bootstrap.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)), \
                patch.object(bootstrap, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "Python 3.10"):
                bootstrap.install("uv")
            run.assert_not_called()
        self.assertEqual(self.marker.read_text(), "keep this environment")

    def test_new_environment_uses_selected_managed_python(self):
        def create_environment(*command):
            if command[1] == "venv":
                self.env.mkdir()
        with patch.object(bootstrap, "run", side_effect=create_environment) as run:
            bootstrap.install("uv")
        run.assert_any_call("uv", "venv", "--python", bootstrap.sys.executable, self.env)
        self.assertFalse(self.pending.exists())

    def test_failed_install_blocks_launch_then_retries_in_place(self):
        self.existing()
        with patch.object(bootstrap.sys, "argv", ["bootstrap.py", "--uv", "uv"]), \
                patch.object(bootstrap.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), \
                patch.object(bootstrap.subprocess, "call", return_value=0) as launch, \
                patch.object(bootstrap, "run", side_effect=subprocess.CalledProcessError(1, ["uv", "pip"])) as run:
            self.assertEqual(bootstrap.main(), 1)
            launch.assert_not_called()
            self.assertTrue(self.pending.exists())
            run.reset_mock()
            run.side_effect = None
            self.assertEqual(bootstrap.main(), 0)
            installers = [call.args for call in run.call_args_list if call.args[1] == "pip"]
            self.assertEqual(len(installers), 1)
            command = installers[0]
            self.assertEqual(command[command.index("--python") + 1], self.python)
            self.assertIn("--reinstall", command)
            self.assertFalse(any(call.args[1] == "venv" for call in run.call_args_list))
            self.assertFalse(self.pending.exists())
            launch.assert_called_once()
        self.assertEqual(self.marker.read_text(), "keep this environment")

    def test_failed_import_or_final_check_leaves_pending_marker(self):
        self.existing()
        for failure in ("-c", "--check"):
            with self.subTest(failure=failure):
                def fail_check(*command):
                    if command[0] == self.python and failure in command:
                        raise subprocess.CalledProcessError(1, list(map(str, command)))
                with patch.object(bootstrap.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), \
                        patch.object(bootstrap, "run", side_effect=fail_check):
                    with self.assertRaises(subprocess.CalledProcessError):
                        bootstrap.install("uv")
                self.assertTrue(self.pending.exists())

    def test_launch_arguments_and_exit_status_are_preserved(self):
        with patch.object(bootstrap.sys, "argv", ["bootstrap.py", "--uv", "uv", "--port", "8877", "--no-browser"]), \
                patch.object(bootstrap, "install"), \
                patch.object(bootstrap.subprocess, "call", return_value=17) as launch:
            self.assertEqual(bootstrap.main(), 17)
        launch.assert_called_once_with([str(self.python), str(self.root / "app.py"), "--port", "8877", "--no-browser"], cwd=self.root)


if __name__ == "__main__":
    unittest.main()
