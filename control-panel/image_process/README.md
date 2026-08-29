# image_process

三方 Agent OCI 镜像构建服务。接收 backend 的构建请求，基于宿主机 Docker 将 agent `.tgz` 构建为 OCI 镜像。默认只保留 Docker daemon 中的镜像；可按配置额外导出 tarball。

上传、鉴权、任务持久化与镜像注册由 control-panel backend 负责；本服务仅提供构建执行与状态查询，经 `image-build` 内网访问，不对宿主暴露端口。

## 目录结构

```text
image_process/
├── Dockerfile           # 本服务镜像（agentos-image-process）
├── base.Dockerfile      # Agent 基座镜像（agent-base:1.0）
├── agent.Dockerfile     # 产物构建模板（FROM agent-base）
├── pyproject.toml
├── app/
│   ├── main.py          # FastAPI 入口
│   ├── config.py
│   ├── schemas.py
│   ├── tasks.py         # 内存任务表与异步执行
│   ├── builder.py       # Docker runtime 封装
│   └── factory/         # Recipe 注册、匹配和构建编排
└── tests/
```

## API

监听 `0.0.0.0:8091`（仅 `image-build` 内网）。

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | Docker 不可用时 503 |
| `POST` | `/v1/builds` | 入队构建，202；必填 `package_path` |
| `GET` | `/v1/builds/{request_id}` | 查询状态；不存在 404 |
| `POST` | `/v1/images/remove` | 按 tag 卸载本机已 load 镜像 |

`POST /v1/builds` 请求体：

```json
{
  "package_path": "/home/agentos/images/packages/<sha256>.artifact",
  "request_id": "optional-id",
  "options": {}
}
```

名称、版本、Recipe、Base 由工厂解析后随构建结果返回。任务状态：`pending` → `building` → `done` | `failed`。任务记录保存在进程内存中，单副本部署。归档关闭时，构建结果的 `archive_path` 为 `null`。

## 部署依赖

Compose 服务名 `image-process`，镜像 `agentos-image-process:latest`（预构建后 load/pull，compose 不负责 build）。挂载：

- `/run/docker.sock` — 使用宿主机 Docker
- `${AGENTOS_BASE:-/home/agentos}/images` — 与 agentos 共享软件包和可选归档目录
- `/tmp/image_process` — Docker daemon 可访问的临时构建上下文

backend 通过 `IMAGE_PROCESS_URL=http://image-process:8091` 调用。构建时 `FROM` 固定为宿主机上的 `agent-base:1.0`。

## 归档配置

| 环境变量 | 默认值 | 说明 |
|------|------|------|
| `THIRDPARTY_AGENT_ARCHIVE_ENABLED` | `false` | 是否在构建后执行 `docker save \| gzip` |
| `OUTPUT_DIR` | `/home/agentos/images` | 归档开启时的输出目录 |
| `WORK_DIR` | `/tmp/image_process/work` | 临时构建目录 |

单机部署建议保持默认值 `false`，避免 Docker daemon 镜像和压缩归档重复占用空间。多机分发需要归档时设置：

```env
THIRDPARTY_AGENT_ARCHIVE_ENABLED=true
THIRDPARTY_AGENT_IMAGE_DIR=/home/agentos/images
```

`save_archive()` 与 `load_archive()` 始终保留，开关只控制 Recipe 是否调用导出方法。

> **NOTE:** 注册中心 v1.3.0 只在 `runtime_spec.rootfs.imageurl` 保存镜像 tag，不保存本机归档路径。管理面删除卡片时从该字段删除 Docker daemon 镜像；归档开启时根据受控输出目录和本地 Agent 元数据推导归档路径。

> **TODO(registry-contract):** 注册中心正式提供独立的启动命令、Recipe/Base 和归档元数据字段后，再替换当前兼容映射；管理面不应直接访问注册中心数据库。

## 镜像构建

在 `control-panel/` 下执行：

```bash
docker build -t agentos-image-process:latest image_process
# 该Dockerfile默认安装每日构建的yuanrong SDK，使用--no-cache选项可以强制使用最新版本的yuanrong SDK，通过传递参数YR_SDK_URL可以指定版本
docker build --no-cache -f image_process/base.Dockerfile -t agent-base:1.0 image_process
```

运行时需要 `agentos-image-process:latest` 与 `agent-base:1.0`。若从制品包 load（tag 形如 `*-<oe-tag>-arm64`），核对后 retag：

```bash
docker images | grep -E 'agent-base|agentos-image-process'

# 示例：oe-tag = 24.03-lts-sp4
docker tag agent-base:1.0-24.03-lts-sp4-arm64 agent-base:1.0
docker tag agentos-image-process:24.03-lts-sp4-arm64 agentos-image-process:latest
```
