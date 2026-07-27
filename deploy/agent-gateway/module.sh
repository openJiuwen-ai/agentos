#!/usr/bin/env bash
# ============================================================
# 模块: agent-gateway (当前仅含 A2X 注册中心 + rqlite 存储，systemd 托管)
# 钩子函数: agent-gateway_up / agent-gateway_down / agent-gateway_install / agent-gateway_uninstall
# ============================================================

AGENTREGISTRY_SVC="agent-registry"
AGENTREGISTRY_UNIT="/etc/systemd/system/${AGENTREGISTRY_SVC}.service"
AGENTREGISTRY_DROPIN_DIR="/etc/systemd/system/${AGENTREGISTRY_SVC}.service.d"
AGENTREGISTRY_DROPIN="${AGENTREGISTRY_DROPIN_DIR}/env.conf"

# 监听地址：--hosts 首个 IP，否则本机网卡 IP
_agentregistry_bind() {
    local ip="${CLUSTER_HOSTS:-}"
    ip="${ip%%,*}"
    [ -z "${ip}" ] && ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    [ -z "${ip}" ] && ip=$(ip route get 1 2>/dev/null | awk '{print $7; exit}')
    echo "${ip:-127.0.0.1}"
}

# ===== install: 装 rqlite rpm + 注册中心 whl，生成 systemd unit =====
agent-gateway_install() {
    local rpm whl py pm
    rpm=$(ls "${AGENTOS_ROOT}"/rqlite-*.rpm 2>/dev/null | sort -V | tail -n1)
    whl=$(ls "${AGENTOS_ROOT}"/a2x_registry-*-py3-none-any.whl 2>/dev/null | sort -V | tail -n1)
    [ -n "${rpm}" ] || error "rqlite rpm not found in ${AGENTOS_ROOT}"
    [ -n "${whl}" ] || error "registry whl not found in ${AGENTOS_ROOT}"

    pm=$(command -v dnf || command -v yum) || error "neither dnf nor yum found"
    "${pm}" install -y "${rpm}" || error "Failed to install rqlite rpm"
    # --break-system-packages 兼容 PEP 668 externally-managed 环境
    "python${YR_PYTHON_VERSION}" -m pip install "${whl}" --quiet --break-system-packages \
        || error "Failed to install a2x-registry whl"

    py=$(command -v "python${YR_PYTHON_VERSION}") || error "python${YR_PYTHON_VERSION} not found"
    cat > "${AGENTREGISTRY_UNIT}" <<EOF
[Unit]
Requires=rqlited.service
After=rqlited.service
[Service]
ExecStart=${py} -m a2x_registry.backend
Restart=on-failure
RestartSec=3
StartLimitIntervalSec=60
StartLimitBurst=5
[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    success "agent-gateway installed"
}

# ===== up: 现算 BIND 设环境变量，起 rqlited + 注册中心，健康检查 =====
agent-gateway_up() {
    local bind port endpoint i
    if systemctl is-active --quiet "${AGENTREGISTRY_SVC}"; then
        warning "agent-gateway already running; run 'down' first to restart"
        return 0
    fi
    systemctl cat rqlited >/dev/null 2>&1 || error "rqlited.service not found; run 'install' first"
    command -v curl >/dev/null 2>&1 || error "curl not found (required for health check)"

    bind=$(_agentregistry_bind)
    port="${A2X_REGISTRY_PORT:-4003}"
    endpoint="${A2X_REGISTRY_DB_ENDPOINT:-http://127.0.0.1:4001}"
    info "Starting agent-gateway on ${bind}:${port} (db: ${endpoint})"

    mkdir -p "${AGENTREGISTRY_DROPIN_DIR}"
    cat > "${AGENTREGISTRY_DROPIN}" <<EOF
[Service]
Environment=A2X_REGISTRY_BIND=${bind}
Environment=A2X_REGISTRY_PORT=${port}
Environment=A2X_REGISTRY_MODE=appliance
Environment=A2X_REGISTRY_DB_KIND=rqlite
Environment=A2X_REGISTRY_DB_ENDPOINT=${endpoint}
EOF
    systemctl daemon-reload
    systemctl enable --now rqlited "${AGENTREGISTRY_SVC}" || error "Failed to start rqlited or ${AGENTREGISTRY_SVC}"

    for i in $(seq 1 15); do
        curl -sf --noproxy '*' -o /dev/null "http://${bind}:${port}/api/datasets" \
            && { success "agent-gateway up on http://${bind}:${port}"; return 0; }
        sleep 1
    done
    error "agent-gateway not healthy in 15s, see: journalctl -u ${AGENTREGISTRY_SVC}"
}

# ===== down: 停服务（rqlited 仅注册中心使用，随之停用） =====
agent-gateway_down() {
    systemctl disable --now "${AGENTREGISTRY_SVC}" rqlited 2>/dev/null \
        && success "agent-gateway stopped" || warning "agent-gateway not running"
}

# ===== uninstall: 停服务 + 删 unit + 卸 whl/rpm =====
agent-gateway_uninstall() {
    systemctl disable --now "${AGENTREGISTRY_SVC}" rqlited 2>/dev/null || true
    rm -rf "${AGENTREGISTRY_UNIT}" "${AGENTREGISTRY_DROPIN_DIR}"
    systemctl daemon-reload
    "python${YR_PYTHON_VERSION}" -m pip uninstall -y a2x-registry || true
    rpm -e rqlite 2>/dev/null || true
    success "agent-gateway uninstalled"
}
