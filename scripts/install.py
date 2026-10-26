#!/usr/bin/env python3
"""Build and install a per-user copy without editing Noctalia or Hyprland config."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib

from project_files import PLUGIN_FILES, ROOT

PLUGIN_ID = "magnus/screen-blackout"
DIRECTORY = "magnus-screen-blackout"


def default_data_home() -> Path:
    override = os.environ.get("NOCTALIA_DATA_HOME")
    if override:
        return Path(override).expanduser()
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    return base / "noctalia"


def check_owned_install(destination: Path) -> None:
    if destination.is_symlink() or not destination.is_dir():
        raise ValueError("Refusing to replace or remove a symlink or non-directory")
    manifest = destination / "plugin.toml"
    if manifest.is_symlink():
        raise ValueError("Refusing to use an installation with a symlinked manifest")
    try:
        identity = tomllib.loads(manifest.read_text()).get("id")
    except (OSError, ValueError):
        raise ValueError("The existing directory is not a recognised plugin installation") from None
    if identity != PLUGIN_ID:
        raise ValueError("The existing directory belongs to a different plugin")


def restore_installed(destination: Path) -> None:
    script = destination / "blackout.py"
    if script.is_symlink() or not script.is_file():
        raise ValueError("The installed recovery helper is missing or symlinked")
    subprocess.run([sys.executable, "-B", str(script), "restore-all"], check=True, timeout=15)


def install(data_home: Path, *, replace: bool = False) -> Path:
    destination = data_home / "plugins" / DIRECTORY
    exists = destination.exists() or destination.is_symlink()
    if exists:
        check_owned_install(destination)
        if not replace:
            raise ValueError("The plugin is already installed; disable it and use --replace to keep a backup")
    data_home.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    with tempfile.TemporaryDirectory(prefix=".screen-blackout-install-", dir=data_home) as temporary:
        staged = Path(temporary) / "contents"
        staged.mkdir()
        for name in PLUGIN_FILES:
            source = ROOT / "screen-blackout" / name
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"Missing or unsafe source file: {name}")
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        subprocess.run(["bash", str(staged / "build-helper.sh")], check=True)
        if exists:
            restore_installed(destination)
            suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            backup = data_home / "screen-blackout-backups" / suffix
            backup.parent.mkdir(parents=True, exist_ok=True)
            destination.rename(backup)
        try:
            staged.rename(destination)
        except OSError:
            if backup is not None and not destination.exists():
                backup.rename(destination)
            raise
    print(f"Installed: {destination}")
    if backup is not None:
        print(f"Previous installation preserved: {backup}")
    print("Enable magnus/screen-blackout in Noctalia and add its toggle widget to the bar.")
    return destination


def uninstall(data_home: Path) -> None:
    destination = data_home / "plugins" / DIRECTORY
    check_owned_install(destination)
    restore_installed(destination)
    shutil.rmtree(destination)
    print(f"Removed: {destination}")
    print("Remove the bar widget and any optional keybindings you added.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-home", type=Path, default=default_data_home(), help="Noctalia data directory; default honours NOCTALIA_DATA_HOME and XDG_DATA_HOME")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--replace", action="store_true", help="Back up and replace an existing installation of this plugin")
    operation.add_argument("--uninstall", action="store_true", help="Recover and remove this plugin's installation")
    args = parser.parse_args(argv)
    data_home = args.data_home.expanduser().absolute()
    try:
        if args.uninstall:
            uninstall(data_home)
        else:
            install(data_home, replace=args.replace)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Installation error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
