# 如何构建 AgentOS 安装包

本指南介绍用仓库自带脚本产出可分发的 `AgentOS-Client.tgz` 与 `AgentOS-Server-<arch>.tgz`。构建机无需部署目标环境，只需 Bash 4.3+、`curl` / `wget`，并可访问华为云 OBS 与 gitcode.com。

## 选择构建脚本

| 脚本 | 适用场景 | 产物 |
|------|----------|------|
| `build/build.sh` | 通用 daily / release 打包（逐包下载 + git clone） | Client、Server 两个 tgz |
| `build/build-v2.sh` | b050 产品线（统一从 OBS `last_successful_build` archive 拉取） | Client、Server、Buildinfo 三个 tgz |

## 方式一：build.sh

```bash
# daily 构建（默认，从 OBS 拉取每日构建产物）
./build/build.sh

# release 构建（固定版本发布包；各组件版本参数见 build/README.zh.md）
./build/build.sh release

# 网络不稳定时降低并行下载数
./build/build.sh daily --download-jobs 1
```

常用参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `daily` / `release` | `daily` | 构建模式（位置参数） |
| `--cp-tag` | `cp311` | agent-runtime wheel 的 Python ABI tag |
| `--jiuwenswarm-release-version` | `0.2.2` | release 模式 jiuwenswarm wheel 版本 |
| `--jiuwenswarm-release-git-tag` | `JiuwenSwarm0.2.2` | release 模式 jiuwenswarm git tag |
| `--download-jobs` | `3` | 并行下载数 |

> 各组件版本、OBS 构建时间戳等完整参数见 [build/README.zh.md](../../../build/README.zh.md)。

## 方式二：build-v2.sh（b050 产品线）

参数统一 `--key=value` 形式：

```bash
# daily
./build/build-v2.sh --build-type=daily --build-target=agentos_b050

# release
./build/build-v2.sh --build-type=release --build-target=agentos_b050

# 在 x86_64 机器上出 aarch64 产物
ARCH=aarch64 ./build/build-v2.sh --build-type=release --build-target=agentos_b050
```

| 参数 | 说明 |
|------|------|
| `--build-type=` | 必填，`daily` 或 `release` |
| `--build-target=` | 交付产品线分支（OBS 归档目录），默认 `agentos_b050` |
| `ARCH` 环境变量 | 目标架构，默认取本机 `uname -m` |

## 产物

产物位于 `build/dist/`（已加入 .gitignore）：

| 产物 | 内容 |
|------|------|
| `AgentOS-Client.tgz` | 全平台 jiuwenswarm_tui wheel（macOS / Windows / Linux x86_64 / aarch64） |
| `AgentOS-Server-<arch>.tgz` | 服务端 whl / rpm + `deploy/` 部署脚本 |
| `AgentOS-Buildinfo.tgz`（仅 v2） | 各部件构建信息汇总，用于版本追溯 |

## 常见问题

- **下载大文件报 `curl: (18) transfer closed`**：OBS 大包并行过多易断连，用 `--download-jobs 1` 降低并发。
- **中途中断后重试**：脚本每次构建先清空 `build/dist/`；残留的 `.part` 临时文件可手动删除。

完整参数、OBS 路径规则与产物目录结构见 [build/README.zh.md](../../../build/README.zh.md) 与 [build/README-v2.zh.md](../../../build/README-v2.zh.md)。
