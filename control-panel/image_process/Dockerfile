# AgentOS image_process — build service (uses host docker via socket)
ARG BASE_OS_IMAGE=openeuler/openeuler:24.03-lts
FROM ${BASE_OS_IMAGE}

# Bundle Docker CLI; talk to host daemon via mounted /run/docker.sock.
# Do not bind-mount host /usr/bin/docker (Docker Desktop often mounts it as an empty dir).
ARG DOCKER_CLI_VERSION=27.5.1
# BuildKit sets TARGETARCH (amd64/arm64). Override with --build-arg DOCKER_CLI_ARCH=...
ARG TARGETARCH
ARG DOCKER_CLI_ARCH=

RUN set -eux; \
    arch="${DOCKER_CLI_ARCH}"; \
    if [ -z "${arch}" ]; then arch="${TARGETARCH}"; fi; \
    if [ -z "${arch}" ]; then arch="$(uname -m)"; fi; \
    case "${arch}" in \
      amd64|x86_64) docker_arch=x86_64 ;; \
      arm64|aarch64) docker_arch=aarch64 ;; \
      *) echo "unsupported arch: ${arch}" >&2; exit 1 ;; \
    esac; \
    yum install -y python3 python3-pip gzip curl; \
    curl -fsSL --retry 5 --retry-delay 2 --retry-all-errors \
        "https://download.docker.com/linux/static/stable/${docker_arch}/docker-${DOCKER_CLI_VERSION}.tgz" \
        -o /tmp/docker.tgz; \
    tar -xzf /tmp/docker.tgz -C /tmp; \
    mv /tmp/docker/docker /usr/local/bin/docker; \
    chmod +x /usr/local/bin/docker; \
    rm -rf /tmp/docker /tmp/docker.tgz; \
    yum clean all; rm -rf /var/cache/yum

WORKDIR /opt/image_process

COPY pyproject.toml ./
COPY app ./app
COPY agent.Dockerfile base.Dockerfile ./

RUN python3 -m venv .venv \
    && .venv/bin/pip install --no-cache-dir -e .

EXPOSE 8091

CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8091"]
