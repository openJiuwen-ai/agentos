FROM openeuler/openeuler:24.03-lts
ARG NODE_VERSION=24.18.0
ARG ARCH=arm64
ARG SDK_BASE_URL=https://build-logs.openeuler.openatom.cn:38080/temp-archived/openeuler/openYuanrong/yr_daily/aarch64/20260718/
ARG YUANRONG_VERSION=9.9.9
ARG ARCH_LONG=arm64

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

# sshd + agentos user
RUN useradd -m agentos
ENV HOME_DIR=/home/agentos

# entrypoint
RUN echo '#!/bin/sh' > /entrypoint.sh \
    && echo '/usr/sbin/sshd -D -f /home/agentos/.ssh/sshd_config -E /tmp/sshd.log' >> /entrypoint.sh \
    && chmod +x /entrypoint.sh
CMD ["/entrypoint.sh"]

# OpenYuanrong SDK
RUN PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')") \
    && SDK_WHEEL="openyuanrong_sdk-${YUANRONG_VERSION}-cp${PYVER}-cp${PYVER}-manylinux_2_34_${ARCH_LONG}.whl" \
    && curl -fsSL "${SDK_BASE_URL}/${SDK_WHEEL}" -o "/tmp/${SDK_WHEEL}" \
    && pip3 install "/tmp/${SDK_WHEEL}" -i https://mirrors.huaweicloud.com/repository/pypi/simple \
    && rm "/tmp/${SDK_WHEEL}"

USER agentos
WORKDIR ${HOME_DIR}

# sshd_config — non-root, key-only auth on port 2222
RUN mkdir -p .ssh \
    && ssh-keygen -t rsa -f .ssh/ssh_host_rsa_key -N '' \
    && echo 'Port 2222' > .ssh/sshd_config \
    && echo 'PubkeyAuthentication yes' >> .ssh/sshd_config \
    && echo 'PasswordAuthentication no' >> .ssh/sshd_config \
    && echo 'AuthorizedKeysFile /run/openyuanrong/ssh/authorized_keys' >> .ssh/sshd_config \
    && echo 'PidFile /tmp/sshd.pid' >> .ssh/sshd_config \
    && echo 'HostKey /home/agentos/.ssh/ssh_host_rsa_key' >> .ssh/sshd_config \
    && chmod 700 .ssh

