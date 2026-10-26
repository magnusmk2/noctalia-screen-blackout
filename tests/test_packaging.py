"""Packaging checks use temporary data roots and never touch the live desktop."""
from __future__ import annotations

import contextlib
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_project
import install
import release
from project_files import PROJECT_FILES


class PackagingChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="blackout-package-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / "data with spaces" / "noctalia"
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        environment = patch.dict(os.environ, {
            "XDG_RUNTIME_DIR": str(self.runtime),
            "HYPRLAND_INSTANCE_SIGNATURE": "test-packaging-only",
            "NOCTALIA_DATA_HOME": "",
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)

    def test_publication_files_pass_review_checks(self):
        self.assertEqual(check_project.check_project(), [])

    def test_data_home_uses_documented_precedence(self):
        with patch.dict(os.environ, {"NOCTALIA_DATA_HOME": str(self.root / "override"), "XDG_DATA_HOME": str(self.root / "xdg")}):
            self.assertEqual(install.default_data_home(), self.root / "override")
        with patch.dict(os.environ, {"NOCTALIA_DATA_HOME": "", "XDG_DATA_HOME": str(self.root / "xdg")}):
            self.assertEqual(install.default_data_home(), self.root / "xdg/noctalia")

    def test_install_replace_backup_and_uninstall_in_isolated_root(self):
        destination = install.install(self.data)
        self.assertTrue(os.access(destination / "blackout-layer", os.X_OK))
        self.assertEqual(tomllib.loads((destination / "plugin.toml").read_text())["id"], install.PLUGIN_ID)
        self.assertEqual({p.name for p in self.data.iterdir()}, {"plugins"})
        marker = destination / "local-marker.txt"
        marker.write_text("preserve old copy")
        with self.assertRaises(ValueError):
            install.install(self.data)
        install.install(self.data, replace=True)
        self.assertFalse(marker.exists())
        backups = list((self.data / "screen-blackout-backups").iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "local-marker.txt").read_text(), "preserve old copy")
        install.uninstall(self.data)
        self.assertFalse(destination.exists())
        self.assertTrue(backups[0].exists())

    def test_different_plugin_is_never_replaced_or_removed(self):
        destination = self.data / "plugins" / install.DIRECTORY
        destination.mkdir(parents=True)
        (destination / "plugin.toml").write_text('id = "another/project"\n')
        for action in [lambda: install.install(self.data, replace=True), lambda: install.uninstall(self.data)]:
            with self.assertRaises(ValueError):
                action()
        self.assertTrue(destination.exists())

    def test_symlinked_installation_is_never_replaced_or_removed(self):
        outside = self.root / "outside"
        outside.mkdir()
        destination = self.data / "plugins" / install.DIRECTORY
        destination.parent.mkdir(parents=True)
        destination.symlink_to(outside, target_is_directory=True)
        for action in [lambda: install.install(self.data, replace=True), lambda: install.uninstall(self.data)]:
            with self.assertRaises(ValueError):
                action()
        self.assertTrue(outside.exists())

    def test_build_failure_preserves_existing_installation(self):
        destination = self.data / "plugins" / install.DIRECTORY
        destination.mkdir(parents=True)
        (destination / "plugin.toml").write_text(f'id = "{install.PLUGIN_ID}"\n')
        marker = destination / "sentinel"
        marker.write_text("do not lose this")
        with patch.dict(os.environ, {"CC": "/bin/false"}):
            with self.assertRaises(subprocess.CalledProcessError):
                install.install(self.data, replace=True)
        self.assertEqual(marker.read_text(), "do not lose this")
        self.assertFalse((self.data / "screen-blackout-backups").exists())
        self.assertEqual(list(self.data.glob(".screen-blackout-install-*")), [])

    def test_source_archive_is_reproducible_and_contains_only_reviewed_sources(self):
        output = self.root / "release"
        archive, first = release.build_release(output)
        first_bytes = archive.read_bytes()
        _, second = release.build_release(output)
        self.assertEqual(first, second)
        self.assertEqual(first_bytes, archive.read_bytes())
        self.assertEqual(first, hashlib.sha256(first_bytes).hexdigest())
        with tarfile.open(archive, "r:gz") as bundle:
            members = bundle.getmembers()
            prefix = members[0].name.split("/", 1)[0]
            self.assertEqual({m.name[len(prefix)+1:] for m in members}, set(PROJECT_FILES))
            for member in members:
                self.assertTrue(member.isfile())
                self.assertFalse(member.issym())
                self.assertEqual((member.uid, member.gid, member.mtime), (0, 0, 0))
                self.assertNotIn("..", Path(member.name).parts)
            for executable in ["install.sh", "screen-blackout/build-helper.sh"]:
                self.assertEqual(bundle.getmember(f"{prefix}/{executable}").mode, 0o755)

    def test_release_refuses_symlinked_source(self):
        fixture = self.root / "fixture"
        (fixture / "screen-blackout").mkdir(parents=True)
        (fixture / "screen-blackout/plugin.toml").write_text('version = "1.0.0"\n')
        (fixture / "unexpected").symlink_to(ROOT / "README.md")
        with patch.object(release, "ROOT", fixture), patch.object(release, "PROJECT_FILES", ("unexpected",)):
            with self.assertRaises(ValueError):
                release.build_release(self.root / "output")
        self.assertEqual(list((self.root / "output").iterdir()), [])

    def test_released_source_installs_without_a_git_checkout(self):
        archive, _ = release.build_release(self.root / "release")
        unpacked = self.root / "unpacked"
        unpacked.mkdir()
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(unpacked, filter="data")
        project = next(unpacked.iterdir())
        subprocess.run([sys.executable, "-B", str(project / "scripts/check_project.py")], check=True, capture_output=True)
        subprocess.run([sys.executable, "-B", str(project / "scripts/install.py"), "--data-home", str(self.data)], check=True, capture_output=True)
        self.assertTrue(os.access(self.data / "plugins" / install.DIRECTORY / "blackout-layer", os.X_OK))
        subprocess.run([sys.executable, "-B", str(project / "scripts/install.py"), "--data-home", str(self.data), "--uninstall"], check=True, capture_output=True)
        self.assertFalse((self.data / "plugins" / install.DIRECTORY).exists())


if __name__ == "__main__":
    unittest.main()
