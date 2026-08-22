# AgentOS管理面

## 镜像构建

```Shell
cd control-panel

# 构建管理面主镜像
IMAGE_NAME="agentos-control-panel"
IMAGE_TAG="latest"
docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" -f image/Dockerfile .

# 构建镜像处理模块
IMAGE_NAME="agentos-image-process"
IMAGE_TAG="latest"
docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" -f image_process/Dockerfile image_process

# 构建Agent基础镜像
IMAGE_NAME="agent-base"
IMAGE_TAG="1.0"
# 该Dockerfile默认安装每日构建的yuanrong SDK，使用--no-cache选项可以强制使用最新版本的yuanrong SDK，通过传递参数YR_SDK_URL可以指定版本
docker build --no-cache -t "${IMAGE_NAME}:${IMAGE_TAG}" -f image_process/base.Dockerfile image_process
```

## 支持Skillhub OAuth2认证

管理面内置 OAuth2 授权服务器能力，支持 SkillHub 等第三方应用以标准 OAuth2 授权码模式接入本机用户系统，实现单点登录。

在 `deploy/.env` 中配置以下变量后重建容器。`OAUTH2_CLIENT_ID` 与 `OAUTH2_CLIENT_SECRET` **任一为空时功能整体不启用**。

```bash
# 配置示例
OAUTH2_CLIENT_ID=
# 可以使用命令 openssl rand -hex 32 生成
OAUTH2_CLIENT_SECRET=
# redirect_uri 必须是浏览器可访问的 SkillHub 回调地址，与客户端配置完全一致
OAUTH2_REDIRECT_URI=http://localhost:9002/api/v1/auth/oauth/agentos/callback
OAUTH2_ACCESS_TOKEN_EXPIRE_MINUTES=1440
# OAUTH2_FRONTEND_ORIGIN 必须是浏览器可访问的 SkillHub 前端地址
OAUTH2_FRONTEND_ORIGIN=http://localhost:8090
# OAUTH2_CLIENT_NAME 透传给前端登录/同意页展示的客户端名称（必填，启用 OAuth2 时不能为空）
OAUTH2_CLIENT_NAME=
```
