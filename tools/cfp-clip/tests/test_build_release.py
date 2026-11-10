import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import build_release


class AppPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cfp-source-package-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        for relative in build_release.SOURCE_FILES:
            destination = self.source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(build_release.ROOT / relative, destination)
            destination.chmod(0o666)  # Windows checkouts do not retain the executable bit.
        self.launcher_lf = b"#!/bin/sh\nprintf 'launcher-ready\\n'\n"
        (self.source / "start.command").write_bytes(b"#!/bin/sh\r\nprintf 'launcher-ready\\n'\r\n")
        with patch.object(build_release, "ROOT", self.source):
            self.archive = build_release.app_zip(self.root)

    def test_archive_preserves_manifest_content_and_portable_permissions(self):
        self.assertEqual(self.archive.name, f"{build_release.NAME}.zip")
        with zipfile.ZipFile(self.archive) as bundle:
            expected = [f"{build_release.NAME}/{relative}" for relative in build_release.SOURCE_FILES]
            self.assertEqual(bundle.namelist(), expected)
            self.assertIn(f"{build_release.NAME}/tests/test_build_release.py", expected)
            self.assertIsNone(bundle.testzip())
            for relative, name in zip(build_release.SOURCE_FILES, expected):
                with self.subTest(file=relative):
                    entry = bundle.getinfo(name)
                    self.assertEqual(entry.create_system, 3)
                    self.assertTrue(stat.S_ISREG(entry.external_attr >> 16))
                    self.assertEqual(stat.S_IMODE(entry.external_attr >> 16), 0o755 if relative == "start.command" else 0o644)
                    expected_content = self.launcher_lf if relative == "start.command" else (self.source / relative).read_bytes()
                    self.assertEqual(bundle.read(name), expected_content)

    @unittest.skipUnless(sys.platform == "darwin", "Verify macOS archive extraction and executable launch")
    def test_mac_extraction_can_launch_crlf_source_command(self):
        self.assertIn(b"\r\n", (self.source / "start.command").read_bytes())
        extracted = self.root / "extracted"
        subprocess.run(["ditto", "-x", "-k", str(self.archive), str(extracted)], check=True, capture_output=True)
        launcher = extracted / build_release.NAME / "start.command"
        self.assertEqual(launcher.read_bytes(), self.launcher_lf)
        self.assertEqual(stat.S_IMODE(launcher.stat().st_mode), 0o755)
        self.assertTrue(os.access(launcher, os.X_OK))
        result = subprocess.run([str(launcher)], cwd=extracted, check=True, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.stdout, "launcher-ready\n")


if __name__ == "__main__":
    unittest.main()
