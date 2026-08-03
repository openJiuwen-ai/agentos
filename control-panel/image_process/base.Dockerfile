ARG BASE_OS_IMAGE=openeuler/openeuler:24.03-lts
FROM ${BASE_OS_IMAGE}

ARG TARGETARCH
ARG NODE_VERSION=24.18.0
ARG YUANRONG_VERSION=9.9.9
# Empty = resolve latest openeuler Build Number from OBS daily index (same as build/build.sh).
ARG YR_SCHEDULE_TIME=
# Override when needed; empty values are derived from TARGETARCH / uname.
ARG ARCH=
ARG ARCH_LONG=
ARG SDK_BASE_URL=

RUN sed -i 's|https://repo.openeuler.org|https://repo.huaweicloud.com/openeuler/|g' /etc/yum.repos.d/openEuler.repo \
    && sed -i '/^meta/d' /etc/yum.repos.d/openEuler.repo

# System packages
RUN yum install -y \
        openssh-server curl ca-certificates findutils python3 python3-pip \
    && yum clean all && rm -rf /var/cache/yum

# Node.js (Huawei Cloud mirror); Node uses linux-x64 / linux-arm64 naming
RUN set -eux; \
    arch="${ARCH}"; \
    if [ -z "${arch}" ]; then arch="${TARGETARCH}"; fi; \
    if [ -z "${arch}" ]; then arch="$(uname -m)"; fi; \
    case "${arch}" in \
      amd64|x86_64) node_arch=x64 ;; \
      arm64|aarch64) node_arch=arm64 ;; \
      *) echo "unsupported arch: ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://mirrors.huaweicloud.com/nodejs/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${node_arch}.tar.gz" \
        -o /tmp/node.tar.gz \
    && tar -xzf /tmp/node.tar.gz -C /usr/local --strip-components=1 \
    && rm /tmp/node.tar.gz
ENV PATH="/usr/local/bin:${PATH}"

# agentos user + ssh dir
RUN useradd -m agentos \
    && mkdir -p /opt/agent-ssh /run/openyuanrong/ssh \
    && chown -R agentos:agentos /opt/agent-ssh /run/openyuanrong/ssh
ENV HOME_DIR=/home/agentos

# entrypoint — start sshd in background, then exec user command
RUN echo '#!/bin/sh' > /entrypoint.sh \
    && echo 'mkdir -p /home/agentos/logs' >> /entrypoint.sh \
    && echo '/usr/sbin/sshd -f /opt/agent-ssh/sshd_config -E /home/agentos/logs/sshd.log &' >> /entrypoint.sh \
    && echo 'exec "$@"' >> /entrypoint.sh \
    && chmod +x /entrypoint.sh

# OpenYuanrong SDK (root install); OBS daily URL aligned with build/build.sh
RUN set -eux; \
    arch="${ARCH}"; \
    arch_long="${ARCH_LONG}"; \
    if [ -z "${arch}" ]; then arch="${TARGETARCH}"; fi; \
    if [ -z "${arch}" ]; then arch="$(uname -m)"; fi; \
    case "${arch}" in \
      amd64|x86_64) arch=amd64; : "${arch_long:=x86_64}" ;; \
      arm64|aarch64) arch=arm64; : "${arch_long:=aarch64}" ;; \
      *) echo "unsupported arch: ${arch}" >&2; exit 1 ;; \
    esac; \
    sdk_base="${SDK_BASE_URL}"; \
    yr_schedule="${YR_SCHEDULE_TIME}"; \
    if [ -z "${sdk_base}" ]; then \
      if [ -z "${yr_schedule}" ]; then \
        html="$(curl -fsSL --retry 3 --retry-delay 2 --connect-timeout 30 --max-time 60 \
          https://openyuanrong.obs.cn-southwest-2.myhuaweicloud.com/daily_build/index.html)"; \
        yr_schedule="$(printf '%s\n' "${html}" \
          | sed -n '/<h2>openeuler<\/h2>/,/<hr class="os-divider">/p' \
          | sed -n 's/.*<tr><td>\([0-9][0-9]*\)<\/td>.*/\1/p' \
          | head -1)"; \
        if [ -z "${yr_schedule}" ]; then \
          yr_schedule="$(printf '%s\n' "${html}" \
            | grep -oE 'daily_build/[0-9]+/openeuler' \
            | head -1 \
            | sed -E 's|daily_build/([0-9]+)/openeuler|\1|')"; \
        fi; \
        if [ -z "${yr_schedule}" ]; then \
          echo "failed to resolve latest yuanrong daily build from OBS index" >&2; \
          exit 1; \
        fi; \
        echo "resolved yuanrong daily build: ${yr_schedule}"; \
      fi; \
      sdk_base="https://openyuanrong.obs.cn-southwest-2.myhuaweicloud.com/daily_build/${yr_schedule}/openeuler/${arch_long}"; \
    fi; \
    sdk_base="${sdk_base%/}"; \
    PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')"); \
    SDK_WHEEL="openyuanrong_sdk-${YUANRONG_VERSION}-cp${PYVER}-cp${PYVER}-manylinux_2_34_${arch_long}.whl"; \
    echo "installing ${SDK_WHEEL} from ${sdk_base}"; \
    curl -fsSL "${sdk_base}/${SDK_WHEEL}" -o "/tmp/${SDK_WHEEL}"; \
    pip3 install "/tmp/${SDK_WHEEL}" -i https://mirrors.huaweicloud.com/repository/pypi/simple; \
    rm "/tmp/${SDK_WHEEL}"

USER agentos
WORKDIR ${HOME_DIR}

# sshd_config + host key — non-root, key-only auth on port 2222
RUN mkdir -p /opt/agent-ssh \
    && ssh-keygen -t rsa -f /opt/agent-ssh/ssh_host_rsa_key -N '' \
    && echo 'Port 2222' > /opt/agent-ssh/sshd_config \
    && echo 'PubkeyAuthentication yes' >> /opt/agent-ssh/sshd_config \
    && echo 'PasswordAuthentication no' >> /opt/agent-ssh/sshd_config \
    && echo 'AuthorizedKeysFile /run/openyuanrong/ssh/authorized_keys' >> /opt/agent-ssh/sshd_config \
    && echo 'PidFile /tmp/sshd.pid' >> /opt/agent-ssh/sshd_config \
    && echo 'HostKey /opt/agent-ssh/ssh_host_rsa_key' >> /opt/agent-ssh/sshd_config

ENTRYPOINT ["/entrypoint.sh"]
CMD ["sleep", "infinity"]
