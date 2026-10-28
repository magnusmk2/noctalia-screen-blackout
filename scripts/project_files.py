"""Explicit source allowlists shared by installation and release packaging."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_FILES = (
    "plugin.toml", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md",
    "widget.luau", "panel.luau", "blackout.py", "blackout-layer.c",
    "build-helper.sh", "wlr-layer-shell-unstable-v1.xml", "tests/test_blackout.py",
)
ROOT_FILES = (
    ".gitignore", ".gitattributes", ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    ".github/dependabot.yml", ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml", ".github/ISSUE_TEMPLATE/config.yml",
    "README.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md", "CHANGELOG.md",
    "catalog.toml", "install.sh", "assets/preview.svg", "docs/PUBLISHING.md",
    "scripts/project_files.py", "scripts/install.py", "scripts/release.py",
    "scripts/check_project.py", "tests/test_packaging.py",
)
PROJECT_FILES = tuple(sorted(ROOT_FILES + tuple(f"screen-blackout/{name}" for name in PLUGIN_FILES)))
