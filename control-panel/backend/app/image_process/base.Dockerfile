FROM openeuler/openeuler:24.03-lts
ARG NODE_VERSION=24.18.0
ARG ARCH=arm64
ARG SDK_BASE_URL=https://build-logs.openeuler.openatom.cn:38080/temp-archived/openeuler/openYuanrong/yr_daily/aarch64/20260718/
ARG YUANRONG_VERSION=9.9.9
ARG ARCH_LONG=aarch64

RUN sed -i 's|https://repo.openeuler.org|https://repo.huaweicloud.com/openeuler/|g' /etc/yum.repos.d/openEuler.repo \
    && sed -i '/^meta/d' /etc/yum.repos.d/openEuler.repo 
# System packages
RUN yum install -y \
        openssh-server curl ca-certificates findutils python3 python3-pip \
    && yum clean all && rm -rf /var/cache/yum

# Node.js (Huawei Cloud mirror)
RUN curl -fsSL https://mirrors.huaweicloud.com/nodejs/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${ARCH}.tar.gz \
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

# OpenYuanrong SDK (root install)
RUN PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')") \
    && SDK_WHEEL="openyuanrong_sdk-${YUANRONG_VERSION}-cp${PYVER}-cp${PYVER}-manylinux_2_34_${ARCH_LONG}.whl" \
    && curl -fsSL "${SDK_BASE_URL}/${SDK_WHEEL}" -o "/tmp/${SDK_WHEEL}" \
    && pip3 install "/tmp/${SDK_WHEEL}" -i https://mirrors.huaweicloud.com/repository/pypi/simple \
    && rm "/tmp/${SDK_WHEEL}"

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

