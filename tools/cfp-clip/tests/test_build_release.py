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


class SourcePackageTests(unittest.TestCase):
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
        (self.source / "start.command").write_text("#!/bin/sh\nprintf 'launcher-ready\\n'\n")
        with patch.object(build_release, "ROOT", self.source):
            self.archive = build_release.source_zip(self.root)

    def test_archive_preserves_manifest_content_and_portable_permissions(self):
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
                    self.assertEqual(bundle.read(name), (self.source / relative).read_bytes())

    @unittest.skipUnless(sys.platform == "darwin", "Verify macOS archive extraction and executable launch")
    def test_mac_extraction_can_launch_source_command(self):
        extracted = self.root / "extracted"
        subprocess.run(["ditto", "-x", "-k", str(self.archive), str(extracted)], check=True, capture_output=True)
        launcher = extracted / build_release.NAME / "start.command"
        self.assertTrue(os.access(launcher, os.X_OK))
        result = subprocess.run([str(launcher)], cwd=extracted, check=True, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.stdout, "launcher-ready\n")


if __name__ == "__main__":
    unittest.main()
