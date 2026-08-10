#!/usr/bin/env bash
# ============================================================
# 模块: agent-gateway (A2X 注册中心 + sqlite 存储)
# 优先使用 systemd 托管；无 systemd 时回退到 nohup 后台进程。
# 钩子函数: agent-gateway_up / agent-gateway_down / agent-gateway_install / agent-gateway_uninstall
# ============================================================

# ===== 端口号 =====
A2X_REGISTRY_PORT="${A2X_REGISTRY_PORT:-4003}"

# ===== mTLS 证书路径（三者齐全=开双向 TLS，空=纯 http） =====
A2X_REGISTRY_TLS_CERTFILE="${A2X_REGISTRY_TLS_CERTFILE:-}"
A2X_REGISTRY_TLS_KEYFILE="${A2X_REGISTRY_TLS_KEYFILE:-}"
A2X_REGISTRY_TLS_CA_CERTS="${A2X_REGISTRY_TLS_CA_CERTS:-}"

# ===== 公共常量 =====
YR_PYTHON_VERSION="${YR_PYTHON_VERSION:-3.11}"
HEALTH_CHECK_RETRIES="${HEALTH_CHECK_RETRIES:-15}"
STOP_WAIT_RETRIES="${STOP_WAIT_RETRIES:-10}"

# ===== systemd 模式常量 =====
AGENTREGISTRY_SVC="agent-registry"
AGENTREGISTRY_UNIT="/etc/systemd/system/${AGENTREGISTRY_SVC}.service"
AGENTREGISTRY_DROPIN_DIR="/etc/systemd/system/${AGENTREGISTRY_SVC}.service.d"
AGENTREGISTRY_DROPIN="${AGENTREGISTRY_DROPIN_DIR}/env.conf"

# ===== nohup 模式常量 =====
AGENTGW_RUN_DIR="${AGENTGW_RUN_DIR:-/var/run/agent-registry}"
AGENTGW_LOG_DIR="${AGENTGW_LOG_DIR:-/var/log/agent-registry}"

REGISTRY_PID_FILE="${AGENTGW_RUN_DIR}/agent-registry.pid"
REGISTRY_LOG="${AGENTGW_LOG_DIR}/agent-registry.log"

# ===== 检测 systemd 是否可用 =====
_agentgw_has_systemd() {
    command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]
}

# ===== 检测是否配置了 mTLS（三者齐全才算开启） =====
_agentregistry_tls_enabled() {
    [ -n "${A2X_REGISTRY_TLS_CERTFILE}" ] && [ -n "${A2X_REGISTRY_TLS_KEYFILE}" ] && [ -n "${A2X_REGISTRY_TLS_CA_CERTS}" ]
}

# 监听地址：--hosts 首个 IP，否则本机网卡 IP
_agentregistry_bind() {
    local ip="${CLUSTER_HOSTS:-}"
    ip="${ip%%,*}"
    [ -z "${ip}" ] && ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    [ -z "${ip}" ] && ip=$(ip route get 1 2>/dev/null | awk '{print $7; exit}')
    echo "${ip:-127.0.0.1}"
}

# ===== nohup 模式辅助函数 =====
# 后台拉起一个进程并记录 PID
_start_bg() {
    local name="$1"; shift
    local pidfile="$1"; shift
    local logfile="$1"; shift
    info "Starting ${name}..."
    nohup "$@" >>"${logfile}" 2>&1 &
    echo $! >"${pidfile}"
}

# 通过 PID 文件停止进程；PID 失效则按命令行 pattern 兜底
_stop_bg() {
    local name="$1" pidfile="$2"; shift 2
    local pid=""
    [ -f "${pidfile}" ] && pid=$(cat "${pidfile}" 2>/dev/null)
    if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
        kill "${pid}" 2>/dev/null || true
        local i
        for i in $(seq 1 "${STOP_WAIT_RETRIES}"); do
            kill -0 "${pid}" 2>/dev/null || break
            sleep 1
        done
        if kill -0 "${pid}" 2>/dev/null; then
            warning "${name} did not exit on SIGTERM, sending SIGKILL"
            kill -9 "${pid}" 2>/dev/null || true
        fi
        success "${name} stopped (pid ${pid})"
    else
        if [ $# -gt 0 ] && pkill -f "$*" >/dev/null 2>&1; then
            success "${name} stopped (by pattern: $*)"
        else
            warning "${name} not running"
        fi
    fi
    rm -f "${pidfile}"
}

# ===== install: 装注册中心 whl，准备运行环境 =====
agent-gateway_install() {
    local whl py
    whl=$(ls "${AGENTOS_ROOT}"/a2x_registry-*-py3-none-any.whl 2>/dev/null | sort -V | tail -n1)
    [ -n "${whl}" ] || error "registry whl not found in ${AGENTOS_ROOT}"

    # 校验 Python（与 yuanrong 共用同一 Python 环境）
    info "Checking Python ${YR_PYTHON_VERSION}..."
    local py_check
    py_check=$("python${YR_PYTHON_VERSION}" --version 2>&1 || echo "not_installed")
    case "${py_check}" in
        *"not_installed"*|*"command not found"*|*"No module"*)
            error "Python ${YR_PYTHON_VERSION} is not installed. Please install it manually before deploying."
            ;;
    esac
    success "Python ${YR_PYTHON_VERSION} available: ${py_check}"

    # 确保 pip 可用（与 yuanrong 一致）
    info "Ensuring pip..."
    "python${YR_PYTHON_VERSION}" -m ensurepip 2>/dev/null || true

    # 安装 a2x-registry whl。
    # agent-gateway 在 yuanrong 之后安装，Python 依赖已由 yuanrong 装好，
    # pip install 仅作检查用（依赖满足则无需公网）。
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

    if _agentgw_has_systemd; then
        info "systemd detected, generating unit file..."
        local py_bindir py_libdir
        py_bindir=$(dirname "${py}")
        py_libdir=$(dirname "${py}")/lib

        cat > "${AGENTREGISTRY_UNIT}" <<EOF
[Unit]
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=5
[Service]
ExecStart=${py} -m a2x_registry.backend
Environment=PATH=${py_bindir}:${PATH}
Environment=LD_LIBRARY_PATH=${py_libdir}:${LD_LIBRARY_PATH:-}
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF

        systemctl daemon-reload
    else
        info "systemd not available, using nohup mode..."
        mkdir -p "${AGENTGW_RUN_DIR}" "${AGENTGW_LOG_DIR}"
    fi

    success "agent-registry installed"
}

# ===== up: 现算 BIND 设环境变量，起注册中心，健康检查 =====
agent-gateway_up() {
    local bind port i scheme curl_tls
    bind=$(_agentregistry_bind)
    port="${A2X_REGISTRY_PORT}"
    info "Starting agent-registry on ${bind}:${port} (db: sqlite)"

    command -v curl >/dev/null 2>&1 || error "curl not found (required for health check)"

    # 部分配置证书视为错误，避免误以为开了 TLS 实则裸 http
    if { [ -n "${A2X_REGISTRY_TLS_CERTFILE}" ] || [ -n "${A2X_REGISTRY_TLS_KEYFILE}" ] || [ -n "${A2X_REGISTRY_TLS_CA_CERTS}" ]; } \
        && ! _agentregistry_tls_enabled; then
        error "TLS certs partially set; provide all of A2X_REGISTRY_TLS_CERTFILE/KEYFILE/CA_CERTS or none"
    fi
    # mTLS 开启时：健康检查改 https，并复用服务端证书作客户端证书
    scheme="http"; curl_tls=()
    if _agentregistry_tls_enabled; then
        scheme="https"
        curl_tls=(--cacert "${A2X_REGISTRY_TLS_CA_CERTS}" --cert "${A2X_REGISTRY_TLS_CERTFILE}" --key "${A2X_REGISTRY_TLS_KEYFILE}")
    fi

    if _agentgw_has_systemd; then
        if systemctl is-active --quiet "${AGENTREGISTRY_SVC}"; then
            warning "agent-registry already running; run 'down' first to restart"
            return 0
        fi

        mkdir -p "${AGENTREGISTRY_DROPIN_DIR}"
        cat > "${AGENTREGISTRY_DROPIN}" <<EOF
[Service]
Environment=A2X_REGISTRY_BIND=${bind}
Environment=A2X_REGISTRY_PORT=${port}
Environment=A2X_REGISTRY_MODE=appliance
Environment=A2X_REGISTRY_DB_KIND=sqlite
EOF
        if _agentregistry_tls_enabled; then
            cat >> "${AGENTREGISTRY_DROPIN}" <<EOF
Environment=A2X_REGISTRY_TLS_CERTFILE=${A2X_REGISTRY_TLS_CERTFILE}
Environment=A2X_REGISTRY_TLS_KEYFILE=${A2X_REGISTRY_TLS_KEYFILE}
Environment=A2X_REGISTRY_TLS_CA_CERTS=${A2X_REGISTRY_TLS_CA_CERTS}
EOF
        fi
        systemctl daemon-reload
        systemctl enable --now "${AGENTREGISTRY_SVC}" || error "Failed to start ${AGENTREGISTRY_SVC}"

        for i in $(seq 1 "${HEALTH_CHECK_RETRIES}"); do
            curl -sf --noproxy '*' "${curl_tls[@]}" -o /dev/null "${scheme}://${bind}:${port}/api/images" \
                && { success "agent-registry up on ${scheme}://${bind}:${port}"; return 0; }
            sleep 1
        done
        error "agent-registry not healthy in 15s, see: journalctl -u ${AGENTREGISTRY_SVC}"
    else
        local py py_bindir py_libdir
        if [ -f "${REGISTRY_PID_FILE}" ] && kill -0 "$(cat "${REGISTRY_PID_FILE}" 2>/dev/null)" 2>/dev/null; then
            warning "agent-registry already running; run 'down' first to restart"
            return 0
        fi
        py=$(command -v "python${YR_PYTHON_VERSION}") || error "python${YR_PYTHON_VERSION} not found"
        py_bindir=$(dirname "${py}")
        py_libdir=$(dirname "${py}")/lib

        mkdir -p "${AGENTGW_RUN_DIR}" "${AGENTGW_LOG_DIR}"

        if _agentregistry_tls_enabled; then
            export A2X_REGISTRY_TLS_CERTFILE A2X_REGISTRY_TLS_KEYFILE A2X_REGISTRY_TLS_CA_CERTS
        fi
        PATH="${py_bindir}:${PATH}" \
        LD_LIBRARY_PATH="${py_libdir}:${LD_LIBRARY_PATH:-}" \
        A2X_REGISTRY_BIND="${bind}" \
        A2X_REGISTRY_PORT="${port}" \
        A2X_REGISTRY_MODE=appliance \
        A2X_REGISTRY_DB_KIND=sqlite \
            _start_bg agent-registry "${REGISTRY_PID_FILE}" "${REGISTRY_LOG}" \
                "${py}" -m a2x_registry.backend

        for i in $(seq 1 "${HEALTH_CHECK_RETRIES}"); do
            curl -sf --noproxy '*' "${curl_tls[@]}" -o /dev/null "${scheme}://${bind}:${port}/api/images" \
                && { success "agent-registry up on ${scheme}://${bind}:${port}"; return 0; }
            sleep 1
        done
        error "agent-registry not healthy in 15s, see: ${REGISTRY_LOG}"
    fi
}

# ===== down: 停服务 =====
agent-gateway_down() {
    if _agentgw_has_systemd; then
        systemctl stop "${AGENTREGISTRY_SVC}" 2>/dev/null \
            && success "agent-registry stopped" || warning "agent-registry not running"
    else
        _stop_bg agent-registry "${REGISTRY_PID_FILE}" "python${YR_PYTHON_VERSION}" -m a2x_registry.backend || true
        success "agent-registry stopped"
    fi
}

# ===== uninstall: 停服务 + 清理 + 卸 whl =====
agent-gateway_uninstall() {
    if _agentgw_has_systemd; then
        systemctl disable --now "${AGENTREGISTRY_SVC}" 2>/dev/null || true
        rm -rf "${AGENTREGISTRY_UNIT}" "${AGENTREGISTRY_DROPIN_DIR}"
        systemctl daemon-reload
    else
        _stop_bg agent-registry "${REGISTRY_PID_FILE}" "python${YR_PYTHON_VERSION}" -m a2x_registry.backend || true
        rm -rf "${AGENTGW_RUN_DIR}" "${AGENTGW_LOG_DIR}"
    fi
    "python${YR_PYTHON_VERSION}" -m pip uninstall -y a2x-registry || true
    success "agent-registry uninstalled"
}
