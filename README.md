# AgentOS

AgentOS 仓库通过 Git Submodule 引入以下依赖，均位于仓库根目录：

| 目录 | 仓库 | 固定版本 |
|------|------|----------|
| `yuanrong/` | [openeuler/yuanrong](https://gitcode.com/openeuler/yuanrong) | `v0.8.0` |
| `jiuwenswarm/` | [openJiuwen/jiuwenswarm](https://gitcode.com/openJiuwen/jiuwenswarm) | `JiuwenSwarm0.2.2` |
| `skill-store/` | [openJiuwen/agent-store](https://gitcode.com/openJiuwen/agent-store) | 主仓库记录的 commit |
| `Conch/` | [openeuler/Conch](https://gitcode.com/openeuler/Conch) | 主仓库记录的 commit |

## 克隆仓库

首次克隆时一并拉取 submodule：

```bash
git clone --recurse-submodules https://gitcode.com/<your-org>/agentos.git
```

若已克隆但未初始化 submodule：

```bash
git submodule update --init --recursive
```

## 更新 submodule

拉取主仓库最新代码后，同步 submodule 到主仓库记录的 commit：

```bash
git submodule update --init --recursive
```

如需将某个 submodule 切换到指定 tag（以 `yuanrong` 为例）：

```bash
cd yuanrong
git fetch --tags
git checkout v0.8.0
cd ..
git add yuanrong
```

## 构建

发布包构建说明见 [build/README.md](build/README.md)。
