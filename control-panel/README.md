# AgentOS管理面

镜像构建

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
