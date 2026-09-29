# How to Build AgentOS Packages

This guide shows how to produce the distributable `AgentOS-Client.tgz` and `AgentOS-Server-<arch>.tgz` with the scripts shipped in this repository. The build machine does not need the deployment target environment — only Bash 4.3+, `curl` / `wget`, and access to Huawei Cloud OBS and gitcode.com.

## Choose a build script

| Script | Use case | Artifacts |
|--------|----------|-----------|
| `build/build.sh` | General daily / release packaging (per-package download + git clone) | Client, Server (2 tgz) |
| `build/build-v2.sh` | b050 product line (pulls OBS `last_successful_build` archives) | Client, Server, Buildinfo (3 tgz) |

## Option 1: build.sh

```bash
# daily build (default, pulls daily artifacts from OBS)
./build/build.sh

# release build (pinned versions; per-component version options in build/README.zh.md)
./build/build.sh release

# lower download parallelism on an unstable network
./build/build.sh daily --download-jobs 1
```

Common options:

| Option | Default | Description |
|--------|---------|-------------|
| `daily` / `release` | `daily` | Build mode (positional) |
| `--cp-tag` | `cp311` | Python ABI tag of agent-runtime wheels |
| `--jiuwenswarm-release-version` | `0.2.2` | jiuwenswarm wheel version (release mode) |
| `--jiuwenswarm-release-git-tag` | `JiuwenSwarm0.2.2` | jiuwenswarm git tag (release mode) |
| `--download-jobs` | `3` | Max concurrent downloads |

> For per-component version pins, OBS build timestamps, and other full options, see [build/README.zh.md](../../../build/README.zh.md).

## Option 2: build-v2.sh (b050 product line)

All options use the `--key=value` form:

```bash
# daily
./build/build-v2.sh --build-type=daily --build-target=agentos_b050

# release
./build/build-v2.sh --build-type=release --build-target=agentos_b050

# produce aarch64 artifacts on an x86_64 host
ARCH=aarch64 ./build/build-v2.sh --build-type=release --build-target=agentos_b050
```

| Option | Description |
|--------|-------------|
| `--build-type=` | Required, `daily` or `release` |
| `--build-target=` | Delivery product-line branch (OBS archive directory), default `agentos_b050` |
| `ARCH` env var | Target architecture, defaults to `uname -m` |

## Artifacts

Artifacts land in `build/dist/` (git-ignored):

| Artifact | Contents |
|----------|----------|
| `AgentOS-Client.tgz` | All-platform jiuwenswarm_tui wheels (macOS / Windows / Linux x86_64 / aarch64) |
| `AgentOS-Server-<arch>.tgz` | Server-side whl / rpm packages + the `deploy/` scripts |
| `AgentOS-Buildinfo.tgz` (v2 only) | Aggregated per-component build info for version tracing |

## FAQ

- **`curl: (18) transfer closed` while downloading large files**: OBS large packages break easily under high parallelism; lower it with `--download-jobs 1`.
- **Retrying after an interrupted build**: every build first clears `build/dist/`; leftover `.part` temp files can be deleted manually.

For the full parameter list, OBS path rules, and artifact directory layout, see [build/README.zh.md](../../../build/README.zh.md) and [build/README-v2.zh.md](../../../build/README-v2.zh.md).
