"""Run ready launchers from a folder with spaces, without network access."""
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
        for name in ("start.command", "start.bat", "bootstrap.py", "requirements.txt", "scripts/start.ps1"):
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        (self.source / "app.py").write_text(
            'import json, pathlib, sys\n'
            'pathlib.Path("launch.json").write_text(json.dumps({'
            '"args": sys.argv[1:], "version": list(sys.version_info[:2])}))\n'
        )
        venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(self.source / ".venv")
        self.python = self.source / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        site = Path(subprocess.check_output([str(self.python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True).strip())
        metadata = site / "pillow-11.3.0.dist-info"
        metadata.mkdir()
        (metadata / "METADATA").write_text("Metadata-Version: 2.1\nName: Pillow\nVersion: 11.3.0\n")
        self.environment = dict(os.environ, CI="1", UV_OFFLINE="1", PIP_NO_INDEX="1",
                                HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9")
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

    def test_ready_environment_restarts_offline_and_preserves_arguments(self):
        for args in (("--no-browser", "--port", "9001"), ("argument with spaces",)):
            result = self.launch(*args)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            record = json.loads((self.source / "launch.json").read_text())
            self.assertEqual(record["args"], list(args))
            self.assertEqual(record["version"], list(sys.version_info[:2]))
            self.assertFalse((self.source / ".bootstrap").exists())
            marker = self.source / ".venv" / "keep.txt"
            if marker.exists():
                self.assertEqual(marker.read_text(), "existing environment")
            marker.write_text("existing environment")

    @unittest.skipUnless(os.name == "nt", "Windows directory-change failure regression")
    def test_failed_directory_change_never_runs_caller_files(self):
        (self.root / "scripts").mkdir()
        (self.root / "scripts/start.ps1").write_text("New-Item -ItemType File caller-code-ran\n")
        launcher = self.source / "start.bat"
        contents = launcher.read_text()
        self.assertIn('cd /d "%~dp0"', contents)
        launcher.write_text(contents.replace('cd /d "%~dp0"', f'cd /d "{self.root / "missing folder"}"'))
        result = self.launch()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Could not open the CFP Crop folder", result.stdout)
        self.assertFalse((self.root / "caller-code-ran").exists())
        self.assertFalse((self.source / "launch.json").exists())


if __name__ == "__main__":
    unittest.main()
