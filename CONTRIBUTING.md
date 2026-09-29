# 贡献指南

感谢你对 AgentOS 的关注！本文说明参与贡献的方式与要求。

## 贡献流程

1. Fork 仓库并创建特性分支（如 `feat/my-feature`、`fix/my-bugfix`）。
2. 完成开发与自测（见下文"测试要求"）。
3. 提交 Pull Request 到主仓库，描述清楚背景、变更点与影响面。
4. 等待维护者评审，按评审意见迭代。

## 测试要求

- 提交前运行仓库自测脚本，UT / ST 全部通过：

  ```bash
  ./ci/run_ci.sh                 # 全部（UT + ST）
  ./ci/run_ci.sh --type=ut       # 仅 UT
  ./ci/run_ci.sh --type=st       # 仅 ST
  ```

- 涉及 `deploy/` 的变更，建议在干净的 openEuler / Ubuntu 环境实际走一遍单机部署（见 [快速开始教程](docs/zh/tutorial/01-quick-start.md)）。

## 代码规范

- Shell 脚本使用 `#!/usr/bin/env bash`，启用 `set -euo pipefail`（参考 `deploy/agentos.sh`）。
- 文件与目录命名使用 kebab-case（全小写，单词间中划线）。
- 新增部署组件遵循[模块钩子约定](docs/zh/how-to/add-deploy-module.md)：`deploy/<module>/module.sh` 实现 `up / down / install / uninstall / status` 钩子，并注册到 `MODULES` 数组。

## 文档要求

- **文档随 PR**：功能变更的 PR 必须同步更新相关文档（README、docs、脚本帮助文本）。
- **双语主从**：中文为权威源（`README.zh.md`、`docs/zh/`），英文跟随（`README.md`、`docs/en/`），两份参数一致、结构对称。
- docs 按 Diátaxis 四类归位：教程（tutorial，数字前缀编号）、操作指南（how-to）、参考（reference）、解释（explanation），一文件一主题；详见 [docs/README.zh.md](docs/README.zh.md)。
- 临时文件（如 `.tmp`、`.bak`）不得提交到仓库。

## 版本发布

本仓无独立 CHANGELOG.md，版本更新信息通过 GitCode [Release](https://gitcode.com/openJiuwen/agent-os/releases) 管理。
