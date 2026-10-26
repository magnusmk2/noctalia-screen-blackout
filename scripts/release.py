#!/usr/bin/env python3
"""Create a reproducible source archive from the reviewed file allowlist."""
import argparse
import gzip
import hashlib
import io
from pathlib import Path
import tarfile
import tomllib

from project_files import PROJECT_FILES, ROOT


def build_release(output: Path) -> tuple[Path, str]:
    version = tomllib.loads((ROOT / "screen-blackout/plugin.toml").read_text())["version"]
    name = f"noctalia-screen-blackout-{version}"
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"{name}.tar.gz"
    temporary = archive.with_suffix(".tmp")
    try:
        with temporary.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as bundle:
                    for relative in PROJECT_FILES:
                        source = ROOT / relative
                        if source.is_symlink() or not source.is_file():
                            raise ValueError(f"Missing or unsafe release input: {relative}")
                        payload = source.read_bytes()
                        info = tarfile.TarInfo(f"{name}/{relative}")
                        info.size = len(payload)
                        info.mode = 0o755 if source.stat().st_mode & 0o111 else 0o644
                        info.mtime = 0
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        bundle.addfile(info, io.BytesIO(payload))
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = output / f"{archive.name}.sha256"
    checksum.write_text(f"{digest}  {archive.name}\n")
    return archive, digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    archive, digest = build_release(args.output)
    print(f"{archive}\nSHA-256: {digest}")


if __name__ == "__main__":
    main()
