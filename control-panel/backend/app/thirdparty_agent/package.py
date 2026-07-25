"""Agent package metadata extraction — pure functions, no framework dependencies."""

import json
import re
import tarfile
from dataclasses import dataclass
from io import BytesIO

_SCOPE_RE = re.compile(r"^@[^/]+/")
_PLATFORM_RE = re.compile(r"-(?:linux|darwin|win32)-(?:x64|arm64)(?:-musl)?$")


@dataclass
class PackageMeta:
    agent_name: str
    version: str
    display_name: str
    entrypoint: str


def extract_package_meta(content: bytes) -> PackageMeta | None:
    """Parse a .tgz archive and extract agent metadata from package/package.json.

    Returns ``None`` when the archive is invalid or the required fields are missing.
    """
    try:
        with tarfile.open(fileobj=BytesIO(content), mode="r:gz") as tf:
            for member in tf.getmembers():
                if member.name.endswith("package/package.json"):
                    f = tf.extractfile(member)
                    if f is not None:
                        pkg = json.loads(f.read())
                        if "name" not in pkg or "version" not in pkg:
                            return None
                        raw_name = pkg["name"]
                        agent_name = _SCOPE_RE.sub("", raw_name)
                        agent_name = _PLATFORM_RE.sub("", agent_name)
                        version = pkg["version"]
                        display_name = pkg.get("displayName") or pkg["name"]
                        entrypoint = ""
                        if "bin" in pkg:
                            bin_val = pkg["bin"]
                            if isinstance(bin_val, dict):
                                entrypoint = next(iter(bin_val))
                            elif isinstance(bin_val, str):
                                entrypoint = bin_val
                        return PackageMeta(
                            agent_name=agent_name, version=version,
                            display_name=display_name, entrypoint=entrypoint)
    except (tarfile.TarError, json.JSONDecodeError):
        pass
    return None
