ARG BASE_IMAGE=agent-base:1.0

FROM ${BASE_IMAGE}

ARG TGZ_FILE
ARG AGENT_NAME
ARG VERSION

USER root:root

COPY ${TGZ_FILE} /tmp/
RUN mkdir -p /tmp/agent-package \
    && tar xzf /tmp/${TGZ_FILE} -C /tmp/agent-package \
    && mkdir -p /usr/local/bin \
    && find /tmp/agent-package/package -type f -perm -u=x -exec cp {} /usr/local/bin/ \; \
    && rm -rf /tmp/agent-package /tmp/${TGZ_FILE}
ENV PATH="/usr/local/bin:$PATH"

USER agentos:agentos

LABEL agent_name="${AGENT_NAME}"
LABEL version="${VERSION}"
