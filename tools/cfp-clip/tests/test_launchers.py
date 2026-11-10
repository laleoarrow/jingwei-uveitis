"""Run source launchers in isolated folders without downloading dependencies."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import venv


ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="cfp-launcher-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / "source with spaces"
        self.source.mkdir()
        for name in ("start.command", "start.bat"):
            shutil.copy2(ROOT / name, self.source / name)
        (self.source / "PIL.py").write_text('__version__ = "11.3.0"\n')
        (self.source / "app.py").write_text(
            'import json, pathlib, sys\n'
            'pathlib.Path("launch.json").write_text(json.dumps({'
            '"args": sys.argv[1:], "version": list(sys.version_info[:2])}))\n'
        )
        self.environment = os.environ.copy()
        for name in ("PYTHONHOME", "PYTHONPATH"):
            self.environment.pop(name, None)

    def launch(self, *args):
        if os.name == "nt":
            batch_command = subprocess.list2cmdline([str(self.source / "start.bat"), *args])
            command = f'cmd /d /s /c "{batch_command}"'
        else:
            command = ["/bin/bash", str(self.source / "start.command"), *args]
        return subprocess.run(command, cwd=self.root, env=self.environment, input="\n",
                              capture_output=True, text=True, timeout=60)

    def test_source_starts_and_reuses_environment_offline(self):
        for args in (("--no-browser", "--port", "9001"), ("argument with spaces",)):
            result = self.launch(*args)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            record = json.loads((self.source / "launch.json").read_text())
            self.assertEqual(record["args"], list(args))
            self.assertGreaterEqual(record["version"], [3, 10])
            self.assertLess(record["version"], [3, 14])
            marker = self.source / ".venv" / "keep.txt"
            if marker.exists():
                self.assertEqual(marker.read_text(), "existing environment")
            marker.write_text("existing environment")

    @unittest.skipUnless(os.name == "nt", "Windows directory-change failure regression")
    def test_failed_directory_change_never_runs_caller_files(self):
        venv.EnvBuilder(with_pip=False).create(self.root / ".venv")
        sentinel = self.root / "caller-code-ran"
        for name in ("app.py", "PIL.py"):
            (self.root / name).write_text(
                'from pathlib import Path\n'
                'Path("caller-code-ran").touch()\n'
                '__version__ = "11.3.0"\n'
            )
        (self.root / "requirements.txt").write_text("must-not-be-installed\n")
        launcher = self.source / "start.bat"
        contents = launcher.read_text()
        self.assertIn('cd /d "%~dp0"', contents)
        # Inject a missing destination without needing a network share or permissions.
        launcher.write_text(contents.replace('cd /d "%~dp0"',
                                            f'cd /d "{self.root / "missing folder"}"'))
        result = self.launch()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Could not open the CFP Crop folder", result.stdout)
        self.assertFalse(sentinel.exists(), "The launcher executed files from the caller directory")


@unittest.skipIf(os.name == "nt", "POSIX interpreter fixtures; Windows uses the real launcher above")
class PosixVersionTests(LauncherTests):
    def setUp(self):
        super().setUp()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        (self.bin / "dirname").symlink_to(shutil.which("dirname"))
        self.environment["PATH"] = str(self.bin)

    def interpreter(self, path, version):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"#!{sys.executable}\n"
            "import pathlib, sys\n"
            f"sys.version_info = {version!r}\n"
            "if sys.argv[1] == '-c':\n"
            "    sys.path.insert(0, str(pathlib.Path.cwd()))\n"
            "    exec(sys.argv[2])\n"
            "elif sys.argv[1:3] == ['-m', 'venv']:\n"
            "    target = pathlib.Path(sys.argv[3]) / 'bin' / 'python'\n"
            "    target.parent.mkdir(parents=True)\n"
            "    target.write_text(pathlib.Path(__file__).read_text())\n"
            "    target.chmod(0o755)\n"
            "else:\n"
            "    sys.argv = sys.argv[1:]\n"
            "    exec(pathlib.Path(sys.argv[0]).read_text())\n"
        )
        path.chmod(0o755)

    def test_source_starts_and_reuses_environment_offline(self):
        self.interpreter(self.bin / "python3", (3, 14))
        self.interpreter(self.bin / "python3.12", (3, 12))
        super().test_source_starts_and_reuses_environment_offline()
        record = json.loads((self.source / "launch.json").read_text())
        self.assertEqual(record["version"], [3, 12])

    def test_rejects_unsupported_default_without_creating_environment(self):
        self.interpreter(self.bin / "python3", (3, 14))
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Python 3.10-3.13", result.stdout)
        self.assertFalse((self.source / ".venv").exists())

    def test_preserves_unsupported_existing_environment(self):
        self.interpreter(self.source / ".venv" / "bin" / "python", (3, 14))
        self.interpreter(self.bin / "python3.12", (3, 12))
        marker = self.source / ".venv" / "keep.txt"
        marker.write_text("do not replace")
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("existing .venv must use Python 3.10-3.13", result.stdout)
        self.assertEqual(marker.read_text(), "do not replace")
        self.assertFalse((self.source / "launch.json").exists())


if __name__ == "__main__":
    unittest.main()
