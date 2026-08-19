ARG BASE_OS_IMAGE=openeuler/openeuler:24.03-lts
FROM ${BASE_OS_IMAGE}

ARG NODE_VERSION=24.18.0
ARG YR_SDK_URL=

RUN sed -i 's|https://repo.openeuler.org|https://repo.huaweicloud.com/openeuler/|g' /etc/yum.repos.d/openEuler.repo \
    && sed -i '/^meta/d' /etc/yum.repos.d/openEuler.repo

# System packages
RUN yum install -y \
        openssh-server curl ca-certificates findutils python3 python3-pip \
    && yum clean all && rm -rf /var/cache/yum

# Node.js (Huawei Cloud mirror); Node uses linux-x64 / linux-arm64 naming
RUN set -eux; \
    node_arch="$(uname -m)"; \
    case "${node_arch}" in \
      amd64|x86_64) node_arch=x64 ;; \
      arm64|aarch64) node_arch=arm64 ;; \
      *) echo "unsupported arch: ${node_arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://mirrors.huaweicloud.com/nodejs/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${node_arch}.tar.gz" \
        -o /tmp/node.tar.gz \
    && tar -xzf /tmp/node.tar.gz -C /usr/local --strip-components=1 \
    && rm /tmp/node.tar.gz
ENV PATH="/usr/local/bin:${PATH}"

# OpenYuanrong SDK + agent_dx_executor (root install); OBS daily URL aligned with build/build.sh
# executor 是纯 Python wheel(py3-none-any), 与平台 wheel 的 SDK 会被 pip 装到不同 site-packages
# (openEuler 的 purelib=.../lib/... 与 platlib=.../lib64/... 分裂), 造成两个 yr 包。
# 故先装到临时目录, 再把 yr 树合并进 SDK 所在的 platlib, 保证 yr 包单一、import yr.agentexecutor 可用。
RUN set -eux; \
    py_arch="$(uname -m)"; \
    case "${py_arch}" in \
      amd64|x86_64) py_arch=x86_64 ;; \
      arm64|aarch64) py_arch=aarch64 ;; \
      *) echo "unsupported arch: ${py_arch}" >&2; exit 1 ;; \
    esac; \
    if [ -z "${YR_SDK_URL}" ]; then \
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
      sdk_base="https://openyuanrong.obs.cn-southwest-2.myhuaweicloud.com/daily_build/${yr_schedule}/openeuler/${py_arch}"; \
      PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')"); \
      SDK_WHEEL="openyuanrong_sdk-9.9.9-cp${PYVER}-cp${PYVER}-manylinux_2_34_${py_arch}.whl"; \
    else \
      sdk_base=${YR_SDK_URL%/*}; \
      SDK_WHEEL=${YR_SDK_URL##*/}; \
    fi; \
    sdk_base="${sdk_base%/}"; \
    echo "installing ${SDK_WHEEL} from ${sdk_base}"; \
    curl -fsSL "${sdk_base}/${SDK_WHEEL}" -o "/tmp/${SDK_WHEEL}"; \
    pip3 install "/tmp/${SDK_WHEEL}" -i https://mirrors.huaweicloud.com/repository/pypi/simple; \
    rm "/tmp/${SDK_WHEEL}"; \
    \
    sdk_ver=$(printf '%s' "${SDK_WHEEL}" | sed -n 's/^openyuanrong_sdk-\([0-9][0-9.]*\)-.*/\1/p'); \
    EXECUTOR_VER="${sdk_ver:-9.9.9}"; \
    EXECUTOR_WHEEL="agent_dx_executor-${EXECUTOR_VER}-py3-none-any.whl"; \
    echo "installing ${EXECUTOR_WHEEL} from ${sdk_base}"; \
    curl -fsSL "${sdk_base}/${EXECUTOR_WHEEL}" -o "/tmp/${EXECUTOR_WHEEL}"; \
    PLATLIB="$(python3 -c 'import sysconfig; print(sysconfig.get_path("platlib"))')"; \
    mkdir -p /tmp/executor-target; \
    pip3 install --no-cache-dir --target /tmp/executor-target "/tmp/${EXECUTOR_WHEEL}"; \
    cp -a /tmp/executor-target/yr/. "${PLATLIB}/yr/"; \
    cp -a "/tmp/executor-target/agent_dx_executor-${EXECUTOR_VER}.dist-info" "${PLATLIB}/"; \
    rm -rf /tmp/executor-target "/tmp/${EXECUTOR_WHEEL}"

# 在构建最终镜像时改为agentos属主/属组
RUN mkdir -p /opt/agent-ssh \
    && ssh-keygen -t rsa -f /opt/agent-ssh/ssh_host_rsa_key -N '' \
    && echo 'Port 2222' > /opt/agent-ssh/sshd_config \
    && echo 'PubkeyAuthentication yes' >> /opt/agent-ssh/sshd_config \
    && echo 'PasswordAuthentication no' >> /opt/agent-ssh/sshd_config \
    && echo 'AuthorizedKeysFile /run/openyuanrong/ssh/authorized_keys' >> /opt/agent-ssh/sshd_config \
    && echo 'PidFile /tmp/sshd.pid' >> /opt/agent-ssh/sshd_config \
    && echo 'HostKey /opt/agent-ssh/ssh_host_rsa_key' >> /opt/agent-ssh/sshd_config

# entrypoint — start sshd in background, then exec user command
RUN echo '#!/bin/sh' > /entrypoint.sh \
    && echo 'mkdir -p /home/agentos/logs' >> /entrypoint.sh \
    && echo 'SSHD_IP=$(python3 -c "import socket; print(socket.gethostbyname(socket.gethostname()))")' >> /entrypoint.sh \
    && echo '/usr/sbin/sshd -D -f /opt/agent-ssh/sshd_config -o "ListenAddress ${SSHD_IP}" -E /home/agentos/logs/sshd.log &' >> /entrypoint.sh \
    && echo 'exec "$@"' >> /entrypoint.sh \
    && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["sleep", "infinity"]

LABEL agentos.runtime_spec="{\"runtime\":\"python3.11\",\"rootfs\":{\"user\":\"agentos\",\"ports\":[\"tcp:2222\"]}}"
