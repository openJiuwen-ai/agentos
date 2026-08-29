"""Shared helpers for image_process tests."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path


def write_npm_tgz(
    dest: Path,
    *,
    name: str = "demo-linux-x64",
    version: str = "1.0.0",
    bin_entry: str | dict | None = "demo",
    display_name: str | None = None,
    elf_name: str | None = None,
) -> Path:
    """Write a minimal npm-layout .tgz to *dest*."""
    pkg: dict = {"name": name, "version": version}
    if display_name is not None:
        pkg["displayName"] = display_name
    if bin_entry is not None:
        pkg["bin"] = bin_entry
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        payload = json.dumps(pkg).encode()
        info = tarfile.TarInfo(name="package/package.json")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))
        if elf_name:
            elf = b"\x7fELF" + b"\x00" * 20
            elf_info = tarfile.TarInfo(name=f"package/bin/{elf_name}")
            elf_info.size = len(elf)
            tf.addfile(elf_info, io.BytesIO(elf))
    dest.write_bytes(buf.getvalue())
    return dest
