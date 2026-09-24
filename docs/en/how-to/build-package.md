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

# release build (pinned versions)
./build/build.sh release \
  --yuanrong-release-version 0.9.0 \
  --jiuwenswarm-release-version 0.2.2 \
  --jiuwenswarm-release-git-tag JiuwenSwarm0.2.2

# lower download parallelism on an unstable network
./build/build.sh daily --download-jobs 1
```

Common options:

| Option | Default | Description |
|--------|---------|-------------|
| `daily` / `release` | `daily` | Build mode (positional) |
| `--cp-tag` | `cp311` | Python ABI tag of yuanrong wheels |
| `--yuanrong-release-version` | `0.9.0` | openYuanrong version (release mode) |
| `--jiuwenswarm-release-version` | `0.2.2` | jiuwenswarm wheel version (release mode) |
| `--jiuwenswarm-release-git-tag` | `JiuwenSwarm0.2.2` | jiuwenswarm git tag (release mode) |
| `--yuanrong-daily-version` | `9.9.9` | wheel version number (daily mode) |
| `--yr-schedule-time` | auto-detected | OBS build timestamp (daily mode) |
| `--download-jobs` | `3` | Max concurrent downloads |

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

For the full parameter list, OBS path rules, and artifact directory layout, see [build/README.md](../../../build/README.md) and [build/README-v2.md](../../../build/README-v2.md).
