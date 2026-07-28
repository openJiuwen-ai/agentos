# 一体机 Compose 部署与验证指南

五个容器：**Frontend** + **PostgreSQL 18** + **LiteLLM** + **VictoriaMetrics** + **Grafana**。

## 目录结构

```
control-panel/
├── .dockerignore               # 镜像构建上下文忽略规则
├── frontend/                   # Vue 源码
├── backend/                    # API 源码（后续纳入同一镜像）
├── image/                      # 镜像构建（与 frontend 同级；当前仅前端+Nginx）
│   ├── Dockerfile
│   └── nginx.conf
└── deploy/                     # 运行时 compose 与监控配置
    ├── deploy.sh               # 一键部署脚本（完整流程）
    ├── docker-compose.yml
    ├── .env.example
    ├── README.md
    ├── litellm/
    │   └── config.yaml             # LiteLLM Proxy 配置
    ├── node-exporter/
    │   └── node_exporter.service   # systemd unit 文件（deploy.sh 引用）
    ├── victoriametrics/
    │   ├── scrape.yml              # VM promscrape 配置
    │   └── agent-metrics.json      # 采集目标（file_sd）
    └── grafana/
        ├── victoriametrics.yml     # 数据源自动配置（VictoriaMetrics）
        ├── default.yml             # Dashboard 自动加载规则
        ├── vllm-perf.json          # vLLM 性能监控面板
        └── sglang-perf.json        # SGLang 性能监控面板
```

## 服务与端口

宿主机端口必须在 `.env` 中配置（示例见 `.env.example`），compose 不设默认值。

| 服务 | 镜像 | 环境变量 | 示例端口 | 说明 |
|------|------|----------|----------|------|
| `frontend` | `agentos` | `FRONTEND_PORT` | 8080 | CI 构建；Nginx 托管 Vue 静态页 |
| `postgres` | `postgres:18.0` | `POSTGRES_PORT` | 5432 | LiteLLM 数据库 |
| `litellm` | `ghcr.io/berriai/litellm-database:v1.91.1` | `LITELLM_PORT` | 4000 | 推理代理 |
| `victoriametrics` | `victoriametrics/victoria-metrics:v1.135.0` | `VICTORIAMETRICS_PORT` | 8428 | 指标存储 |
| `grafana` | `grafana/grafana:12.4.2` | -- | 3000 | 监控面板 |

**宿主机原生服务（非容器）：**

| 服务 | 二进制 | 端口 | 说明 |
|------|--------|------|------|
| `node_exporter` | `/usr/bin/node_exporter` | 8084 | 主机指标采集（systemd） |

## 配置说明

| 宿主机文件 | 容器内路径 | 作用 |
| ---------- | ---------- | ---- |
| `.env` | compose 环境变量 | PG 密码、LiteLLM master key |
| `litellm/config.yaml` | litellm `/app/config.yaml` | Proxy 配置 |
| `victoriametrics/scrape.yml` | `/etc/vm/scrape.yml` | `-promscrape.config`；勿写 `refresh_interval` |
| `victoriametrics/agent-metrics.json` | `/etc/vm/agent-metrics.json` | 采哪些 Agent（后端常写） |
| `grafana/victoriametrics.yml` | provisioning datasources | 自动连 VM |
| `grafana/default.yml` | provisioning dashboards | Dashboard 加载规则 |
| `grafana/*-perf.json` | `/var/lib/grafana/dashboards/` | 面板 JSON |
| `node-exporter/node_exporter.service` | `/etc/systemd/system/node_exporter.service` | systemd unit（deploy.sh 内联安装） |

生产环境：`agent-metrics.json` 建议放在 `/var/lib/agentos/monitoring/`，compose 改挂载路径即可。

## 前置条件

| 项 | 说明 |
| ---- | ---- |
| Docker | 已安装 Docker Engine + Compose 插件 |
| 端口 | `.env` 中宿主机端口已配置且未被占用 |
| 配置文件 | 上表所列文件齐全 |
| 环境变量 | 复制 `.env.example` → `.env`，修改密码与 master key |
| 前端镜像 | CI 已构建并推送到仓库，或通过 `docker load` 导入本机 |
| systemd | 宿主机使用 systemd init（Ubuntu / Debian / CentOS 等） |
| 网络 | 目标机可访问 GitHub Releases（否则手动下载二进制） |

---

## 部署流程

### 快速部署（一键脚本）

```bash
cd control-panel/deploy

# 三步完成：
sudo bash deploy.sh install     # 安装：.env + 镜像拉取 + node_exporter 注册
sudo bash deploy.sh up          # 启动：node_exporter → docker compose
sudo bash deploy.sh status      # 验证服务状态
```

其他命令：
- `deploy.sh down`      停止：docker compose → node_exporter（反序）
- `deploy.sh uninstall` 卸载：停止服务 + 清理 .env + 注销 systemd

---

### 分步部署

以下为手动分步流程，与一键脚本等价。

### 1. 准备镜像

以手动自验证为例：

**构建前端产物**

```bash
cd control-panel/frontend
./build.sh
```

或手动：

```bash
cd control-panel/frontend
npm ci
npm run build
```

**打包运行镜像**

```bash
cd control-panel
docker build -f image/Dockerfile -t agentos .
# CI 推送到镜像仓库（按实际 registry 修改）
# docker tag agentos your-registry/agentos/agentos:1.0.0
# docker push your-registry/agentos/agentos:1.0.0
```

**拉取公共镜像**

若目标环境没有外网，则从有网环境拉取公共镜像，再打包传到无网环境。

```bash
docker pull postgres:18.0
docker pull ghcr.io/berriai/litellm-database:v1.91.1
docker pull victoriametrics/victoria-metrics:v1.135.0
docker pull grafana/grafana:12.4.2
docker pull nginx:1.29.7-alpine

docker save -o postgres_18.0.tar postgres:18.0
docker save -o litellm-database_v1.91.1.tar ghcr.io/berriai/litellm-database:v1.91.1
docker save -o victoria-metrics_v1.135.0.tar victoriametrics/victoria-metrics:v1.135.0
docker save -o grafana_12.4.2.tar grafana/grafana:12.4.2

docker load -i postgres_18.0.tar
docker load -i litellm-database_v1.91.1.tar
docker load -i victoria-metrics_v1.135.0.tar
docker load -i grafana_12.4.2.tar

docker images | grep -E 'agentos|postgres|litellm|victoria-metrics|grafana'
```


### 2. 部署 node_exporter（宿主机）

node_exporter 运行在宿主机（非容器），提供 CPU / 内存 / 磁盘 / 网络等指标。

前置条件：将解压后的 `node_exporter` 二进制放入 `deploy/node-exporter/` 目录，`deploy.sh install` 会自动拷贝到 `/usr/bin` 并注册 systemd 服务。

**检查状态**：

```bash
systemctl status node_exporter
curl -s http://127.0.0.1:8084/metrics | head -5
```

### 3. 一键拉起（docker compose）

```bash
cd control-panel/deploy

cp .env.example .env
# 编辑 .env：POSTGRES_PASSWORD、LITELLM_MASTER_KEY（须以 sk- 开头）

docker compose pull
docker compose up -d
```

**检查状态**
```bash
# 预期 5 个服务均为 Running（litellm 需等 postgres healthy 后启动，首次约 40s）。
docker compose ps

# 检查 frontend 状态（端口：8080）
curl -I http://127.0.0.1:8080/

# 检查 postgres 状态（端口：5432）：返回的 STATUS 为 healthy
docker ps --filter name=deploy-postgres-1

# 检查 litellm-database 状态（端口：4000）：返回 "I'm alive!"
curl http://127.0.0.1:4000/health/liveliness

# 检查 victoria-metrics 状态（端口：8428）：返回 OK
curl http://127.0.0.1:8428/health

# 检查 grafana 状态（端口：3000）：返回 { database: "ok", version: "12.4.2", ... }
curl http://127.0.0.1:3000/api/health
```

**停止与清理**

```bash
docker compose down
# 清空指标数据
docker compose down -v
```

---

## 性能监控验证

| #   | 检查      | 操作                       | 预期                       |
| --- | --------- | -------------------------- | -------------------------- |
| 1 | 登录      | 打开 http://127.0.0.1:3000 | 匿名 Viewer                |
| 2 | 数据源    | VictoriaMetrics → Test     | 成功                       |
| 3 | Dashboard | **AgentOS** 文件夹         | `vllm-perf`、`sglang-perf` |
| 4 | 面板      | 打开 `vllm-perf`           | 4 个 Panel                 |
| 5 |  `agent-metrics.json`     | 编辑 `agent-metrics.json`         |  （1）grafana 能展示 target 性能数据；<br>（2） `curl "http://127.0.0.1:8428/api/v1/query?query=up{job=\"vllm-9000\"}"` 预期看到 `value` 有值，如 `"value":[..., "1"]`               |