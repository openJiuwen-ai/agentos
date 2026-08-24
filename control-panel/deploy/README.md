# AgentOS 一体机部署与验证指南

> 部署由 `deploy.sh` 脚本驱动，支持 **单机** 与 **多机（master / worker）** 两种拓扑，以及 **交互式（-i）** 与 **非交互式** 两种安装模式。

Compose 管理八个容器：**agentos**（Frontend + Backend + Nginx 单容器）+ **image-process** + **PostgreSQL 18** + **LiteLLM** + **VictoriaMetrics** + **Loki** + **Alloy** + **Grafana**。

## 部署架构

| 拓扑 | 说明 |
|------|------|
| 单机（master） | 容器由 docker compose 管理；`node_exporter` / `npu-exporter` 为宿主机 systemd 服务；Alloy 日志采集由 compose 内的 `alloy` 容器负责 |
| 多机（master + worker） | master 与单机一致；worker 节点不跑 docker compose，仅安装 `node_exporter` / `npu-exporter` / 独立 `alloy`（日志上报到 master 的 Loki）；worker 的指标由 master 的 VictoriaMetrics 经 `WORKER_NODES` 采集 |

## 服务与端口

宿主机端口在 `.env` 中配置（示例见 `.env.example`），compose 不设默认值。

| 服务 | 镜像 | 环境变量 | 默认端口 | 说明 |
|------|------|----------|----------|------|
| `agentos` | `agentos-control-panel` | `FRONTEND_PORT` | 8090 | Frontend + Backend + Nginx 单容器（CI 构建） |
| `image-process` | `agentos-image-process` | -- | （不对宿主暴露） | Agent 镜像构建；仅 `image-build` 内网 |
| `postgres` | `postgres:18.0` | `POSTGRES_PORT` | 5432 | AgentOS 与 LiteLLM 共享数据库 |
| `litellm` | `ghcr.io/berriai/litellm-database:v1.91.1` | `LITELLM_PORT` | 8100 | 推理代理 |
| `victoriametrics` | `victoriametrics/victoria-metrics:v1.135.0` | `VICTORIAMETRICS_PORT` | 8428 | 指标存储 |
| `loki` | `grafana/loki:3.6.0` | -- | 8096 | 日志存储（master） |
| `alloy` | `grafana/alloy:v1.18.1` | -- | 12345 | 日志采集（master 由 compose 管理；worker 独立安装，仅监听 127.0.0.1） |
| `grafana` | `grafana/grafana:12.4.2` | `GRAFANA_PORT` | 8093 | 监控面板（控制台 iframe 走 `FRONTEND_PORT` 的 `/grafana/` 反代） |

**宿主机原生服务（非容器）：**

| 服务 | 二进制安装路径 | 默认端口 | 说明 |
|------|---------------|----------|------|
| `node_exporter` | `/usr/bin/node_exporter` | 8091 | 主机指标采集（systemd） |
| `npu-exporter` | `/usr/local/bin/npu-exporter` | 8092 | NPU 指标采集（systemd timer） |

## 前置条件

| 项 | 说明 |
| ---- | ---- |
| Docker | 已安装 Docker Engine + Compose 插件 |
| 端口 | `.env` 中宿主机端口已配置且未被占用 |
| 环境变量 | `deploy.sh install` 自动从 `.env.example` 生成 `.env`，支持交互/非交互模式 |
| 前端镜像 | CI 已构建并推送到仓库，或通过 `docker load` 导入本机 |
| image-process 镜像 | `docker compose build image-process`（或预先 `docker build -t agentos-image-process ../image_process`） |
| agent-base | 宿主机需已有 `agent-base:1.0`（制品需手动准备） |
| systemd | 宿主机使用 systemd init（Ubuntu / Debian / CentOS 等） |

### 所需版本清单

| 类型 | 名称 | 版本 |
|------|------|------|
| 容器镜像 | `postgres` | `18.0` |
| 容器镜像 | `ghcr.io/berriai/litellm-database` | `v1.91.1` |
| 容器镜像 | `victoriametrics/victoria-metrics` | `v1.135.0` |
| 容器镜像 | `grafana/loki` | `3.6.0` |
| 容器镜像 | `grafana/alloy` | `v1.18.1` |
| 容器镜像 | `grafana/grafana` | `12.4.2` |
| 容器镜像（SkillHub） | `skillhub-backend` | `latest` |
| 容器镜像（SkillHub） | `skillhub-frontend` | `latest` |
| 容器镜像（SkillHub） | `mysql` | `8.0` |
| 容器镜像（SkillHub） | `redis` | `7-alpine` |
| 容器镜像（SkillHub） | `minio/minio` | `RELEASE.2025-09-07T16-13-09Z` |
| 容器镜像（SkillHub） | `minio/mc` | `RELEASE.2025-08-13T08-35-41Z` |
| 二进制文件 | `node_exporter` | `v1.12.1` |
| 二进制文件 | `npu-exporter` | `>26.0.0` |

### 环境变量配置要求

`deploy.sh install` 非交互模式下，以下环境变量可提前设置以覆盖默认值：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `POSTGRES_USER` | `agentos` | PostgreSQL 用户名 |
| `POSTGRES_PASSWORD` | `agentos123` | PostgreSQL 密码 |
| `AGENTOS_ADMIN_USERNAME` | `admin` | 管理后台用户名 |
| `AGENTOS_ADMIN_PASSWORD` | `admin123` | 管理后台密码 |
| `AGENTOS_NODE_ROLE` | `master` | 节点角色：`master` / `worker` |
| `LITELLM_HOST` | 自动检测本机 IP | LiteLLM 监听地址 |
| `NODE_EXPORTER_HOST` | 自动检测本机 IP | node_exporter 监听地址 |
| `NPU_EXPORTER_HOST` | 自动检测本机 IP | npu_exporter 监听地址 |
| `MASTER_IP` | 空 | 仅 worker 节点；master 节点 IP（Alloy 日志上报用） |
| `WORKER_NODES` | `[]` | 仅 master；worker IP 的 JSON 数组，如 `'["192.168.1.11"]'`（建议单引号包裹，仅支持 IPv4） |
| `AGENT_REGISTER_URL` | `http://<本机IP>:4003` | 注册中心地址（留空禁用"智能体监控"） |
| `AGENT_REGISTER_URL` | `http://<本机IP>:4003` | 注册中心地址 |
| `OAUTH2_CLIENT_ID` | 无 | OAuth2客户端ID |
| `OAUTH2_CLIENT_SECRET` | 无 | OAuth2客户端密钥 |
| `OAUTH2_REDIRECT_URI` | 无 | OAuth2客户端回调地址 |
| `OAUTH2_ACCESS_TOKEN_EXPIRE_MINUTES` | 1440 | OAuth2 access token有效时间 |
| `OAUTH2_FRONTEND_ORIGIN` | 无 | AgentOS前端地址 |
| `OAUTH2_CLIENT_NAME` | 无 | 透传给前端登录/同意页展示的客户端名称（启用 OAuth2 时必填，不能为空） |

> 以下密钥由安装脚本自动生成，**无需手动设置**：
> - `AGENTOS_JWT_SECRET_KEY` — JWT 签名密钥
> - `LITELLM_MASTER_KEY` — LiteLLM 管理密钥（sk- 前缀）
> - `LITELLM_KEY_ENCRYPTION_KEY` — LiteLLM 密钥加密密钥

**`up` 启动时还会自动生成/写入以下配置（一般无需手动设置）：**

| 环境变量 | 说明 |
|----------|------|
| `INITIAL_MODELS` | 模型列表 JSON，`deploy.sh up` 从推理服务 `GET /models` 嗅探后写入 |
| `INITIAL_MODEL_API_BASE` | 手动模式（`up --models/--models-file`）写入的推理服务地址 |
| `INITIAL_MODEL_API_KEY` | 手动模式写入的推理服务鉴权 Key |
| `INITIAL_INFERENCE_ENGINE` | 部署框架（`vllm` / `sglang`），由 `owned_by` 推导 |
| `INITIAL_MODEL_METRICS_URL` | 模型监控采集地址（deploy 脚本用，后端不读） |

**端口（`.env` 可调）：**

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `FRONTEND_PORT` | 8090 | agentos 容器宿主端口 |
| `POSTGRES_PORT` | 5432 | PostgreSQL（仅绑定 localhost） |
| `VICTORIAMETRICS_PORT` | 8428 | VictoriaMetrics（仅绑定 localhost） |
| `GRAFANA_PORT` | 8093 | Grafana 直出端口（仅调试用；控制台 iframe 走 `/grafana/` 反代） |
| `LITELLM_PORT` | 8100 | LiteLLM 宿主端口 |
| `NODE_EXPORTER_PORT` | 8091 | node_exporter 监听端口 |
| `NPU_EXPORTER_PORT` | 8092 | npu-exporter 监听端口 |

### 镜像准备

**打包运行镜像**

```bash
cd control-panel
docker build -f image/Dockerfile -t agentos-control-panel .
```

**拉取公共镜像**

若目标环境没有外网，则从有网环境拉取公共镜像，再打包传到无网环境。

```bash
docker pull postgres:18.0
docker pull ghcr.io/berriai/litellm-database:v1.91.1
docker pull victoriametrics/victoria-metrics:v1.135.0
docker pull grafana/loki:3.6.0
docker pull grafana/alloy:v1.18.1
docker pull grafana/grafana:12.4.2

docker save -o postgres_18.0.tar postgres:18.0
docker save -o litellm-database_v1.91.1.tar ghcr.io/berriai/litellm-database:v1.91.1
docker save -o victoria-metrics_v1.135.0.tar victoriametrics/victoria-metrics:v1.135.0
docker save -o loki_3.6.0.tar grafana/loki:3.6.0
docker save -o alloy_v1.18.1.tar grafana/alloy:v1.18.1
docker save -o grafana_12.4.2.tar grafana/grafana:12.4.2

# 目标机：
docker load -i postgres_18.0.tar
docker load -i litellm-database_v1.91.1.tar
docker load -i victoria-metrics_v1.135.0.tar
docker load -i loki_3.6.0.tar
docker load -i alloy_v1.18.1.tar
docker load -i grafana_12.4.2.tar

docker images | grep -E 'agentos|postgres|litellm|victoria-metrics|loki|alloy|grafana'
```

> `deploy.sh install` 中的 `pull_images` 会从 `docker-compose.yml` 自动提取镜像名，逐个检测本地缺失项并拉取；`docker compose config`/`python3` 不可用时按内置清单兜底。

**image-process / agent-base（构建机准备，部署机拉取或 load）**

```bash
cd control-panel
docker build -t agentos-image-process:latest image_process
docker build -f image_process/base.Dockerfile -t agent-base:1.0 image_process

docker save -o agentos-image-process_latest.tar agentos-image-process:latest
docker save -o agent-base_1.0.tar agent-base:1.0

# 目标机：
docker load -i agentos-image-process_latest.tar
docker load -i agent-base_1.0.tar
```

**SkillHub 镜像（仅 `--with-skillhub` 时需要）**

```bash
docker pull mysql:8.0
docker pull redis:7-alpine
docker pull minio/minio:RELEASE.2025-09-07T16-13-09Z
docker pull minio/mc:RELEASE.2025-08-13T08-35-41Z

# skillhub-backend / skillhub-frontend 为私有镜像，需预先构建或从制品库获取
# docker build -t skillhub-backend:latest <path-to-skillhub-backend>
# docker build -t skillhub-frontend:latest <path-to-skillhub-frontend>

docker save -o mysql_8.0.tar mysql:8.0
docker save -o redis_7-alpine.tar redis:7-alpine
docker save -o minio_minio.tar minio/minio:RELEASE.2025-09-07T16-13-09Z
docker save -o minio_mc.tar minio/mc:RELEASE.2025-08-13T08-35-41Z
docker save -o skillhub-backend_latest.tar skillhub-backend:latest
docker save -o skillhub-frontend_latest.tar skillhub-frontend:latest

# 目标机：
docker load -i mysql_8.0.tar
docker load -i redis_7-alpine.tar
docker load -i minio_minio.tar
docker load -i minio_mc.tar
docker load -i skillhub-backend_latest.tar
docker load -i skillhub-frontend_latest.tar
```

### Exporter 准备

Exporter 运行在宿主机（非容器），提供指标采集。`deploy.sh install` 会自动拷贝二进制并注册 systemd 服务。

需要准备的 exporter 及指定版本：

| Exporter | 版本 | 来源 |
|----------|------|------|
| `node_exporter` | v1.12.1 | [GitHub Releases](https://github.com/prometheus/node_exporter/releases/tag/v1.12.1) |
| `npu-exporter` | >26.0.0 | [MindCluster Releases](https://gitcode.com/Ascend/mind-cluster/releases/v26.0.0) |

**node_exporter**

从 [GitHub Releases](https://github.com/prometheus/node_exporter/releases/tag/v1.12.1) 下载对应机器架构的压缩包（如 `linux-amd64`、`linux-arm64` 等），解压后将 `node_exporter` 二进制放入 `deploy/node-exporter/` 目录。

```bash
# 示例（以 linux-amd64 为例，实际根据架构选择）：
# amd64 架构：
wget https://github.com/prometheus/node_exporter/releases/download/v1.12.1/node_exporter-1.12.1.linux-amd64.tar.gz
tar xzf node_exporter-1.12.1.linux-amd64.tar.gz
cp node_exporter-1.12.1.linux-amd64/node_exporter deploy/node-exporter/

# arm64 架构：
wget https://github.com/prometheus/node_exporter/releases/download/v1.12.1/node_exporter-1.12.1.linux-arm64.tar.gz
tar xzf node_exporter-1.12.1.linux-arm64.tar.gz
cp node_exporter-1.12.1.linux-arm64/node_exporter deploy/node-exporter/
```

要求：`deploy/node-exporter/node_exporter` 文件存在，且 `deploy/node-exporter/node_exporter.service` 文件存在（已随仓库提供）。

> **注意**：下载时请根据目标机器的 CPU 架构选择对应的软件包，可通过 `uname -m` 查看本机架构。

**npu-exporter**

从 [MindCluster Releases](https://gitcode.com/Ascend/mind-cluster/releases/v26.1.0) 下载对应机器架构的压缩包，解压后将以下文件放入 `deploy/npu-exporter/` 目录：

| 文件 | 必需 | 说明 |
|------|------|------|
| `npu-exporter` | 是 | 二进制文件 |
| `npu-exporter.service` | 是 | systemd service unit |
| `npu-exporter.timer` | 是 | systemd timer unit |
| `metricConfiguration.json` | 否 | 指标配置（安装时拷贝到 `/usr/local/`） |
| `pluginConfiguration.json` | 否 | 插件配置（安装时拷贝到 `/usr/local/`） |

```bash
# 示例（根据实际包名调整）：
# x86_64 架构：
unzip Ascend-mindxd1-npu-exporter_<version>_linux-x86_64.zip -d deploy/npu-exporter/
# aarch64 架构：
unzip Ascend-mindxd1-npu-exporter_<version>_linux-aarch64.zip -d deploy/npu-exporter/
```

> **注意**：下载时请根据目标机器的 CPU 架构选择对应的软件包（如 `linux-x86_64`、`linux-aarch64`），可通过 `uname -m` 查看本机架构。

---

## 部署流程

### 快速部署（一键脚本）

#### 单机 master

```bash
# 1. 安装（非交互式，自动拷贝到 ~/.agentos/.agent-manager）：
sudo bash deploy.sh install

# 2. 进入安装目录（后续所有操作在此目录执行）：
cd ~/.agentos/.agent-manager

# 3. 启动服务：
sudo bash deploy.sh up

# 4. 查看状态：
sudo bash deploy.sh status
```

交互式安装（逐项询问角色、密码、IP、是否启用多机监控等配置）：

```bash
sudo bash deploy.sh install -i
cd ~/.agentos/.agent-manager
sudo bash deploy.sh up
```

#### 多机部署（master + worker）

master 节点（`--mode multi` + `--workers`；仅传 `--workers` 时自动切换为 multi）：

```bash
sudo bash deploy.sh install --mode multi --workers 192.168.1.11,192.168.1.12
# 等价写法：
sudo bash deploy.sh install --workers 192.168.1.11,192.168.1.12

cd ~/.agentos/.agent-manager
sudo bash deploy.sh up
```

worker 节点（`--role worker` + `--master-ip`）：

```bash
sudo bash deploy.sh install --role worker --master-ip 192.168.1.10

cd ~/.agentos/.agent-manager
sudo bash deploy.sh up
```

> - `--role` / `--mode` / `--workers` / `--master-ip` 为非交互拓扑参数，与 `-i` 互斥。
> - 交互模式（`-i`）安装 master 时，会询问是否启用多机监控并逐个录入 worker IP（输入 `q` 结束）。
> - worker 节点安装后 `up`/`down` 只管理本机 exporter 与 Alloy，不涉及 docker compose。
> - `up` 时若 `WORKER_NODES` 含重复 IP 或与 master 本机相同，脚本会自动规范化并写回 `.env`。

#### 含 SkillHub 部署（预装 skill + OAuth2 SSO）

```bash
# 1. 安装（含 SkillHub 初始化 + 预装 skill 源目录配置）：
sudo bash deploy.sh install --with-skillhub

# 2. 进入安装目录：
cd ~/.agentos/.agent-manager

# 3. 启动服务（含 SkillHub 启动 + 预装 skill 上传到市场）：
sudo PRESET_SKILLS_ZIP=/path/to/preset-skills.zip bash deploy.sh up --with-skillhub

# 4. 查看状态（含 SkillHub 健康检查）：
sudo bash deploy.sh status
```

> - `--with-skillhub` 需预先准备 SkillHub 镜像（见上方"镜像准备"）。
> - `PRESET_SKILLS_ZIP` 指向预装 skill 的 zip 包，启动时自动解压并上传到 SkillHub 市场。
> - SkillHub 前端默认端口 `8098`（`SKILLHUB_FRONTEND_PORT` 可调）。
> - 云服务器部署时需传入公网 IP：`sudo SKILLHUB_HOST=<公网IP> ... bash deploy.sh up --with-skillhub`。

#### 指定模型配置（up）

```bash
# 1. 用 .env 已有配置，或自动嗅探推理服务（GET /models）写入 INITIAL_MODELS
sudo bash deploy.sh up

# 2. 命令行传 JSON（单引号包裹，含 api_base，自包含，无需配 .env）
#    嗅探所有模型：
sudo bash deploy.sh up --models '{"api_base":"http://192.168.1.10:8000/v1","models":[]}'
#    指定模型 + 补全字段：
sudo bash deploy.sh up --models '{"api_base":"http://192.168.1.10:8000/v1","api_key":"sk-xxx","models":[{"id":"qwen2.5-72b","max_model_len":32768}]}'

# 3. 从文件读 JSON（推荐，无需转义）
sudo bash deploy.sh up --models-file /path/to/models.json
```

`models.json` 格式：

```json
{
  "api_base": "http://192.168.1.10:8000/v1",
  "api_key": "sk-xxx",
  "models": [
    {"id": "qwen2.5-72b", "max_model_len": 32768, "owned_by": "vllm"},
    {"id": "glm5.2", "max_model_len": 1048576, "owned_by": "sglang"},
    {"id": "deepseek-v3"}
  ]
}
```

字段说明：

| 字段 | 说明 |
|------|------|
| `api_base` | 必填，推理服务地址（含 `/v1` 或不含，取决于推理服务） |
| `api_key` | 可选，推理服务鉴权 Key |
| `models` | 模型列表；为空 → 嗅探该推理服务所有模型；有内容 → 只校验 + 补全列出的模型 |
| `models[].id` | 可选，模型标识名（填了校验该模型存在，不填无意义） |
| `models[].max_model_len` | 可选，上下文长度（填了与嗅探值校验，不填用嗅探值补全） |
| `models[].owned_by` | 可选，部署框架（填了与嗅探值校验，不填用嗅探值补全） |

> 手动模式会用 `api_base` 嗅探校验：用户填了的字段与嗅探值不一致会报错，未填的字段用嗅探值补全，随后写入 `.env`（`INITIAL_MODEL_API_BASE`、`INITIAL_MODEL_API_KEY`、`INITIAL_MODELS` 等），后端据此注册模型到 LiteLLM。

### 所有命令

| 命令 | 说明 |
|------|------|
| `deploy.sh install` | 安装（默认非交互、单机 master）：初始化 `.env` → 安装 node_exporter → npu-exporter → Alloy → 拉取镜像 |
| `deploy.sh install -i` | 交互式安装（可选 master/worker、多机监控） |
| `deploy.sh install --role master\|worker` | 指定节点角色 |
| `deploy.sh install --mode single\|multi --workers ip1,ip2` | master 多机安装 |
| `deploy.sh install --role worker --master-ip <ip>` | worker 节点指定 master IP |
| `deploy.sh uninstall` | 卸载：停止服务 + 注销 systemd（保留数据和 .env） |
| `deploy.sh uninstall --clean` | 卸载：删除数据卷、.env 和安装目录 |
| `deploy.sh up` | 启动：更新 exporter 配置 → 启动 node/npu_exporter → Alloy → 生成 hardware-metrics.json → 配置模型 → docker compose up |
| `deploy.sh up --models '<JSON>'` | 启动并手动指定模型配置（含 api_base，自包含） |
| `deploy.sh up --models-file <path>` | 启动并从文件读取模型配置 JSON |
| `deploy.sh down` | 停止：docker compose → node/npu_exporter（反序） |
| `deploy.sh restart` | 重启：down → up |
| `deploy.sh status` | 查看服务状态（docker compose ps + 端口健康检查） |

**注意：** `up` / `down` / `restart` / `status` / `uninstall` 需在安装目录 `~/.agentos/.agent-manager` 下执行（deploy.sh 会校验，否则提示先 `cd` 过去）。

**选项：**

| 选项 | 说明 |
|------|------|
| `--interactive, -i` | 交互式安装（与下方拓扑参数互斥） |
| `--clean` | `uninstall` 时删除数据卷、`.env` 和安装目录 |
| `--role master\|worker` | 节点角色，默认 `master` |
| `--mode single\|multi` | 仅 master；默认 `single`；仅传 `--workers` 时自动设为 `multi` |
| `--workers ip1,ip2,...` | master 多机 worker IPv4 列表；可单独传参，`--mode multi` 时必填 |
| `--master-ip <ip>` | 仅 `--role worker`；master 节点 IP（Alloy 日志上报） |
| `--models '<JSON>'` | `up` 时手动指定模型配置 JSON |
| `--models-file <path>` | `up` 时从文件读取模型配置 JSON |
| `--with-skillhub` | 同时部署/启动 SkillHub（默认不启动；需预先准备 SkillHub 镜像） |

---

> **强烈不建议**：以下分步部署流程仅用于特殊场景（如调试、定制化部署）。正常部署请使用上方的一键脚本。

### 分步部署（特殊场景，不优先使用）

#### 1. 准备镜像

**打包运行镜像**

```bash
cd control-panel
docker build -f image/Dockerfile -t agentos-control-panel .
```

**拉取公共镜像**

```bash
docker pull postgres:18.0
docker pull ghcr.io/berriai/litellm-database:v1.91.1
docker pull victoriametrics/victoria-metrics:v1.135.0
docker pull grafana/loki:3.6.0
docker pull grafana/alloy:v1.18.1
docker pull grafana/grafana:12.4.2

docker save -o postgres_18.0.tar postgres:18.0
docker save -o litellm-database_v1.91.1.tar ghcr.io/berriai/litellm-database:v1.91.1
docker save -o victoria-metrics_v1.135.0.tar victoriametrics/victoria-metrics:v1.135.0
docker save -o loki_3.6.0.tar grafana/loki:3.6.0
docker save -o alloy_v1.18.1.tar grafana/alloy:v1.18.1
docker save -o grafana_12.4.2.tar grafana/grafana:12.4.2

# 目标机：
docker load -i postgres_18.0.tar
docker load -i litellm-database_v1.91.1.tar
docker load -i victoria-metrics_v1.135.0.tar
docker load -i loki_3.6.0.tar
docker load -i alloy_v1.18.1.tar
docker load -i grafana_12.4.2.tar
```

#### 2. 部署 node_exporter（宿主机）

node_exporter 运行在宿主机（非容器），提供 CPU / 内存 / 磁盘 / 网络等指标。

前置条件：将解压后的 `node_exporter` 二进制放入 `deploy/node-exporter/` 目录，`deploy.sh install` 会自动拷贝到 `/usr/bin` 并注册 systemd 服务。

```bash
systemctl status node_exporter
curl -s http://127.0.0.1:8091/metrics | head -5
```

#### 3. 拉起 docker compose

```bash
cd control-panel/deploy

cp .env.example .env
# 编辑 .env：POSTGRES_PASSWORD、LITELLM_MASTER_KEY（须以 sk- 开头）

docker compose pull
docker compose up -d
```

**检查状态**

```bash
docker compose ps

curl -I http://127.0.0.1:8090/
docker ps --filter name=deploy-postgres-1
curl http://127.0.0.1:8100/health/liveliness
curl http://127.0.0.1:8428/health
curl http://127.0.0.1:8093/api/health
```

**停止与清理**

```bash
docker compose down
docker compose down -v  # 清空指标数据
```
