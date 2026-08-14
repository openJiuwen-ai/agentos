# image_process

三方 Agent OCI 镜像构建服务。接收 backend 的构建请求，基于宿主机 Docker 将 agent `.tgz` 构建为 OCI 镜像并导出 tarball。

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
│   └── builder.py       # Docker 构建
└── tests/
```

## API

监听 `0.0.0.0:8094`（仅 `image-build` 内网，写死于 Dockerfile）。

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | Docker 不可用时 503 |
| `POST` | `/v1/builds` | 入队构建，202 |
| `GET` | `/v1/builds/{task_id}` | 查询状态；不存在 404 |

`POST /v1/builds` 请求体：

```json
{
  "task_id": "uuid",
  "agent_name": "my-agent",
  "version": "1.0.0",
  "installer_path": "/home/agentos/users/<user>/installers/xxx.tgz",
  "output_dir": "/home/agentos/users/<user>/images",
  "work_dir": null
}
```

`agent_name` / `version` 须匹配 `[a-zA-Z0-9][-a-zA-Z0-9_.]*`。任务状态：`pending` → `building` → `done` | `failed`。任务记录保存在进程内存中，单副本部署。

## 部署依赖

Compose 服务名 `image-process`，镜像 `agentos-image-process:latest`（预构建后 load/pull，compose 不负责 build）。挂载：

- `/run/docker.sock` — 使用宿主机 Docker
- `${AGENTOS_BASE:-/home/agentos}/users` — 与 agentos 共享 installer / 输出目录

backend 通过 `IMAGE_PROCESS_URL=http://image-process:8094` 调用。构建时 `FROM` 固定为宿主机上的 `agent-base:1.0`。

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
