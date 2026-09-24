# AgentOS 示例

本目录提供可运行的示例工程，clone 仓库后配合安装包即可直接使用。

| 示例 | 说明 |
|------|------|
| [single-node-up.sh](single-node-up.sh) | 单机一键部署：解包 → 装依赖 → 配置 config.yaml → 生成 SSH 密钥 → install / init / up → status |

## 运行前提

- 一台满足[环境要求](../README.md)的 Linux 服务器（root 权限）
- 已获取 `AgentOS-Server.tgz` 安装包（[下载](../README.md)或[自行构建](../docs/zh/how-to/build-package.md)）

## 快速使用

```bash
sudo bash examples/single-node-up.sh --package /path/to/AgentOS-Server.tgz

# 多网卡机器显式指定本机 IP：
sudo bash examples/single-node-up.sh --package /path/to/AgentOS-Server.tgz --ip 192.168.100.1
```

脚本完成后访问 `http://<本机IP>:19000` 打开 jiuwenswarm Web 前端。

> 示例脚本仅供参考，请按实际环境修改。逐步操作与每步解释见[快速开始教程](../docs/zh/tutorial/01-quick-start.md)。
