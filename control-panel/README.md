# AgentOS管理面

镜像构建

```Shell
cd control-panel

IMAGE_NAME="agentos-control-panel"
IMAGE_TAG="latest"
docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" -f image/Dockerfile .
```
