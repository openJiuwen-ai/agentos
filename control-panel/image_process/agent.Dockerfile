ARG BASE_IMAGE=agent-base:1.0

FROM ${BASE_IMAGE}

ARG TGZ_FILE
ARG AGENT_NAME
ARG VERSION
ARG AGENTOS_SYS_UID=1000
ARG AGENTOS_SYS_GID=1000

# 使用指定ID创建用户
RUN groupadd -g ${AGENTOS_SYS_GID} agentos \
    && useradd -m agentos -u ${AGENTOS_SYS_UID} -g agentos

# 修复agent-ssh目录权限
RUN chown -R agentos:agentos /opt/agent-ssh

COPY --chown=agentos:agentos ${TGZ_FILE} /tmp/
RUN mkdir -p /tmp/agent-package \
    && tar xzf /tmp/${TGZ_FILE} -C /tmp/agent-package \
    && find /tmp/agent-package/package -type f -perm -u=x -exec cp {} /usr/local/bin/ \; \
    && rm -rf /tmp/agent-package /tmp/${TGZ_FILE}

USER agentos
WORKDIR /home/agentos

LABEL agent_name="${AGENT_NAME}"
LABEL version="${VERSION}"
