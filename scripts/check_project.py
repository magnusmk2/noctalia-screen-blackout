#!/usr/bin/env python3
"""Validate the reviewed public source set, metadata and selected security rules."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET

from project_files import PROJECT_FILES, ROOT

SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
)


def check_project() -> list[str]:
    errors = []
    for relative in PROJECT_FILES:
        source = ROOT / relative
        if source.is_symlink() or not source.is_file():
            errors.append(f"Missing or symlinked publication file: {relative}")
            continue
        data = source.read_bytes()
        if len(data) > 1024 * 1024:
            errors.append(f"Unexpectedly large publication file: {relative}")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"Unexpected binary publication file: {relative}")
            continue
        if "\x00" in text:
            errors.append(f"NUL byte in source file: {relative}")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            errors.append(f"Potential credential/private-key material: {relative}")
        if re.search(r"/home/[A-Za-z0-9_.-]+/", text):
            errors.append(f"Personal absolute home path: {relative}")

    manifest = tomllib.loads((ROOT / "screen-blackout/plugin.toml").read_text())
    catalog = tomllib.loads((ROOT / "catalog.toml").read_text())["plugin"]
    if len(catalog) != 1:
        errors.append("Catalog must contain this plugin only")
    else:
        for key in ["id", "name", "version", "author", "license", "icon", "description", "plugin_api", "tags", "dependencies"]:
            if catalog[0].get(key) != manifest.get(key):
                errors.append(f"Catalog/manifest mismatch: {key}")
    if manifest["id"] != "magnus/screen-blackout" or not re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"]):
        errors.append("Unexpected plugin identity or version")
    if manifest["plugin_api"] != 34 or len(manifest["description"]) > 120:
        errors.append("Unexpected plugin API or catalog description length")
    for entry_type in ["widget", "panel"]:
        for entry in manifest[entry_type]:
            path = ROOT / "screen-blackout" / entry["entry"]
            if not path.is_file() or str(path.relative_to(ROOT)) not in PROJECT_FILES:
                errors.append(f"Missing entry script: {entry['entry']}")
    if (ROOT / "LICENSE").read_text() != (ROOT / "screen-blackout/LICENSE").read_text():
        errors.append("Repository and installed-plugin licences differ")
    protocol = ROOT / "screen-blackout/wlr-layer-shell-unstable-v1.xml"
    copyright_text = ET.parse(protocol).getroot().find("copyright").text
    notices = (ROOT / "screen-blackout/THIRD_PARTY_NOTICES.md").read_text()
    if " ".join(copyright_text.split()) not in " ".join(notices.split()):
        errors.append("Vendored protocol permission notice is not fully preserved")
    if hashlib.sha256(protocol.read_bytes()).hexdigest() not in notices:
        errors.append("Vendored protocol checksum does not match its notice")
    preview = ET.parse(ROOT / "assets/preview.svg").getroot()
    for element in preview.iter():
        if element.tag.rsplit("}", 1)[-1] in {"script", "foreignObject", "image"}:
            errors.append("Preview must contain only original self-contained vector artwork")
        if any(name.rsplit("}", 1)[-1] in {"href", "src"} for name in element.attrib):
            errors.append("Preview must not load external content")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    references = re.findall(r"uses:\s*(\S+)", workflow)
    if not references or any(not re.fullmatch(r"actions/[A-Za-z0-9_-]+@[0-9a-f]{40}", value) for value in references):
        errors.append("Every workflow action must be an explicitly pinned GitHub-owned action")
    for required in ["contents: read", "persist-credentials: false", "timeout-minutes: 10", "pull_request:"]:
        if required not in workflow:
            errors.append(f"Missing workflow safeguard: {required}")
    for forbidden in ["pull_request_target", "secrets.", "contents: write", "id-token: write"]:
        if forbidden in workflow:
            errors.append(f"Unexpected privileged workflow construct: {forbidden}")
    if (ROOT / ".git").exists():
        result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True)
        tracked = {name.decode() for name in result.stdout.split(b"\0") if name}
        if tracked != set(PROJECT_FILES):
            errors.append(f"Tracked source differs from allowlist; missing={sorted(set(PROJECT_FILES)-tracked)}, extra={sorted(tracked-set(PROJECT_FILES))}")
    return errors


if __name__ == "__main__":
    errors = check_project()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps({"publication_files": len(PROJECT_FILES), "checks": "passed", "policy_scope": "See docs/PUBLISHING.md"}))
