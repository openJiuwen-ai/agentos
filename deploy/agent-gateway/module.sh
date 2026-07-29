#!/usr/bin/env bash
# ============================================================
# 模块: agent-gateway (当前仅含 A2X 注册中心 + rqlite 存储，systemd 托管)
# 钩子函数: agent-gateway_up / agent-gateway_down / agent-gateway_install / agent-gateway_uninstall
# ============================================================

YR_PYTHON_VERSION="${YR_PYTHON_VERSION:-3.11}"

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
    local rpm whl py
    rpm=$(ls "${AGENTOS_ROOT}"/rqlite-*.rpm 2>/dev/null | sort -V | tail -n1)
    whl=$(ls "${AGENTOS_ROOT}"/a2x_registry-*-py3-none-any.whl 2>/dev/null | sort -V | tail -n1)
    [ -n "${rpm}" ] || error "rqlite rpm not found in ${AGENTOS_ROOT}"
    [ -n "${whl}" ] || error "registry whl not found in ${AGENTOS_ROOT}"

    # 校验 Python（与 yuanrong 共用同一 Python 环境）
    info "Checking Python ${YR_PYTHON_VERSION}..."
    local py_check
    py_check=$("python${YR_PYTHON_VERSION}" --version 2>&1 || echo "not_installed")
    if [[ "${py_check}" == *"not_installed"* ]] || [[ "${py_check}" == *"command not found"* ]] || [[ "${py_check}" == *"No module"* ]]; then
        error "Python ${YR_PYTHON_VERSION} is not installed. Please install it manually before deploying."
    fi
    success "Python ${YR_PYTHON_VERSION} available: ${py_check}"

    # 确保 pip 可用（与 yuanrong 一致）
    info "Ensuring pip..."
    "python${YR_PYTHON_VERSION}" -m ensurepip 2>/dev/null || true

    rpm -ivh --force --nodeps --replacepkgs "${rpm}" || error "Failed to install rqlite rpm"

    # 安装 a2x-registry whl。
    # pip install 仅作检查用。
    info "Installing a2x-registry whl: $(basename "${whl}")"
    if "python${YR_PYTHON_VERSION}" -m pip install "${whl}" --quiet; then
        # 加固：pip show 确认包确实已注册到当前 Python 环境
        if "python${YR_PYTHON_VERSION}" -m pip show a2x-registry >/dev/null 2>&1; then
            success "a2x-registry whl installed/verified"
        else
            error "pip install returned success but 'pip show a2x-registry' failed (wheel may be corrupted or installed to wrong env)"
        fi
    else
        error "Failed to install a2x-registry whl"
    fi

    py=$(command -v "python${YR_PYTHON_VERSION}") || error "python${YR_PYTHON_VERSION} not found"

    local py_bindir py_libdir
    py_bindir=$(dirname "${py}")
    py_libdir=$(dirname "${py}")/lib
    cat > "${AGENTREGISTRY_UNIT}" <<EOF
[Unit]
Requires=rqlited.service
After=rqlited.service
StartLimitIntervalSec=60
StartLimitBurst=5
[Service]
ExecStart=${py} -m a2x_registry.backend
Environment=PATH=${py_bindir}:$PATH
Environment=LD_LIBRARY_PATH=${py_libdir}:$LD_LIBRARY_PATH
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF

    # rqlited 单节点 drop-in: -node-id + -bootstrap-expect 1 使其自动选主
    local rqlite_dropin_dir="/etc/systemd/system/rqlited.service.d"
    mkdir -p "${rqlite_dropin_dir}"
    cat > "${rqlite_dropin_dir}/single-node.conf" <<EOF
[Service]
ExecStart=
ExecStart=/usr/bin/rqlited -node-id 1 -bootstrap-expect 1 /var/lib/rqlite/data
EOF

    # 清理旧 Raft 状态，确保单节点能重新 bootstrap 为 leader
    systemctl stop rqlited 2>/dev/null || true
    rm -rf /var/lib/rqlite/data/*

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
    # 先启动 rqlited，等其选主完成后再启动 agent-registry
    systemctl enable --now rqlited || error "Failed to start rqlited"
    for i in $(seq 1 15); do
        curl -sf --noproxy '*' "http://127.0.0.1:4001/leader" | grep -q '"node_id"' \
            && break
        sleep 1
    done
    systemctl enable --now "${AGENTREGISTRY_SVC}" || error "Failed to start ${AGENTREGISTRY_SVC}"

    for i in $(seq 1 15); do
        curl -sf --noproxy '*' -o /dev/null "http://${bind}:${port}/api/images" \
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
    rm -rf "${AGENTREGISTRY_UNIT}" "${AGENTREGISTRY_DROPIN_DIR}" \
        "/etc/systemd/system/rqlited.service.d"
    systemctl daemon-reload
    "python${YR_PYTHON_VERSION}" -m pip uninstall -y a2x-registry || true
    rpm -e rqlite 2>/dev/null || true
    success "agent-gateway uninstalled"
}
