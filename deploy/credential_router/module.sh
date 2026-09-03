#!/usr/bin/env bash
# ============================================================
# 模块: credential_router (凭据路由服务，Go 二进制)
# 优先使用 systemd 托管；无 systemd 时回退到 nohup 后台进程。
# 钩子函数: credential_router_up / credential_router_down / credential_router_install / credential_router_uninstall
# CLI: bash module.sh {up|down|install|uninstall|status}
#
# 说明:
#   - install 从 ${AGENTOS_ROOT} 取构建产物 credential-router_linux_<arch>
#     （由顶层 build/build.sh::build_credential_router + pack() 复制进
#     AgentOS-Server-${ARCH}.tgz 根；构建从 credential_router submodule 源码）。
#   - 运行所需内容（二进制 + config + secrets + data）持久化到 ~/.agentos/credential_router。
#   - 健康检查: proxy 8080 /health + admin 8081 /v1/health（端口从 config.yaml 解析）。
#   - 不依赖 Docker；容器环境（无 systemd）自动走 nohup 模式。
# ============================================================

# ===== 端口/健康检查 =====
CR_PROXY_PORT="${CR_PROXY_PORT:-18080}"
CR_ADMIN_PORT="${CR_ADMIN_PORT:-18081}"
CR_ADMIN_IP="${CR_ADMIN_IP:-}"
CR_HEALTH_HOST="${CR_HEALTH_HOST:-127.0.0.1}"
CR_HEALTH_RETRIES="${CR_HEALTH_RETRIES:-15}"
CR_STOP_WAIT_RETRIES="${CR_STOP_WAIT_RETRIES:-10}"

# ===== 目录常量 =====
# 持久化部署根：安装后所有运行所需内容（二进制 + config + secrets + data）统一放这里
CR_HOME="${CR_HOME:-${HOME:-/root}/.agentos/credential_router}"

# ===== systemd 模式常量 =====
CR_SVC="credential-router"
CR_UNIT="${CR_UNIT:-/etc/systemd/system/${CR_SVC}.service}"

# ===== nohup 模式常量 =====
CR_RUN_DIR="${CR_RUN_DIR:-/var/run/credential-router}"
CR_LOG_DIR="${CR_LOG_DIR:-/var/log/credential-router}"
CR_PID_FILE="${CR_RUN_DIR}/credential-router.pid"
CR_LOG="${CR_LOG_DIR}/credential-router.log"

# ===== 检测 systemd 是否可用 =====
_cr_has_systemd() {
    command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]
}

_cr_docker_bridge_ip() {
    ip -4 addr show docker0 2>/dev/null | awk '/inet /{print $2}' | head -1 | cut -d/ -f1
}

# ===== 部署根解析 =====
_cr_deploy_root() {
    [ -d "${CR_HOME}" ] && { echo "${CR_HOME}"; return 0; }
    return 1
}

# ===== 架构标签：uname -m → build.sh 产物标签（x86_64 / arm64）=====
# build.sh 将 aarch64/arm64 统一映射为 arm64 并打包 credential-router_linux_arm64；
# 而 submodule scripts/start.sh 直接用 uname -m 命名（aarch64）。两者都需支持。
_cr_arch_label() {
    case "$(uname -m)" in
        x86_64|amd64) echo "x86_64" ;;
        aarch64|arm64) echo "arm64" ;;
        *) echo "$(uname -m)" ;;
    esac
}

# ===== 二进制定位（兄弟模块约定）：从 AGENTOS_ROOT 取 build.sh 产物 =====
# 与 agent-gateway/jiuwenswarm 一致: ls ${AGENTOS_ROOT}/<产品>-* | sort -V | tail -n1。
# install 完成后二进制同时持久化到 ${CR_HOME}/dist/bin/，up/down 优先使用。
_cr_find_bin() {
    local b
    b=$(ls "${AGENTOS_ROOT}"/credential-router_linux_* 2>/dev/null | sort -V | tail -n1)
    if [ -n "${b}" ] && [ -x "${b}" ]; then
        echo "${b}"
        return 0
    fi
    [ -x "${CR_HOME}/dist/bin/credential-router" ] && { echo "${CR_HOME}/dist/bin/credential-router"; return 0; }
    return 1
}

# ===== 配置定位 =====
_cr_find_config() {
    [ -f "${CR_HOME}/config.yaml" ] && { echo "${CR_HOME}/config.yaml"; return 0; }
    return 1
}

# ===== 从 config.yaml 解析端口（bind_address / admin.addr），失败回退默认值 =====
_cr_config_port() {
    local key="$1" default="$2" cfg val
    cfg=$(_cr_find_config) || { echo "${default}"; return 0; }
    val=$(grep -E "^[[:space:]]*${key}:" "${cfg}" 2>/dev/null | head -n1 | sed -E 's/^[[:space:]]*[^:]+:[[:space:]]*//' || true)
    val="${val%\"*}"
    val="${val#\"}"
    val="${val%\'*}"
    val="${val#\'}"
    if [ -n "${val}" ]; then
        echo "${val##*:}"
    else
        echo "${default}"
    fi
}

# ===== 健康检查：proxy /health + admin /v1/health 双端点 =====
_cr_wait_healthy() {
    local i proxy_port admin_port
    proxy_port=$(_cr_config_port bind_address "${CR_PROXY_PORT}")
    admin_port=$(_cr_config_port addr "${CR_ADMIN_PORT}")
    for i in $(seq 1 "${CR_HEALTH_RETRIES}"); do
        if curl -sf --noproxy '*' -o /dev/null "http://${CR_HEALTH_HOST}:${proxy_port}/health" \
            && curl -sf --noproxy '*' -o /dev/null "http://${CR_HEALTH_HOST}:${admin_port}/v1/health"; then
            return 0
        fi
        sleep 1
    done
    return 1
}

# ===== nohup 模式辅助函数 =====
_cr_start_bg() {
    local name="$1"; shift
    local pidfile="$1"; shift
    local logfile="$1"; shift
    info "Starting ${name}..."
    nohup "$@" >>"${logfile}" 2>&1 &
    echo $! >"${pidfile}"
}

# 通过 PID 文件停止进程；PID 失效则按二进制自写 router.pid（<pid>:<unix_ts>）兜底。
# 不使用 pkill -f "$*"：模糊匹配容易误杀其他进程，且调用方传入的 pattern 不一定唯一。
_cr_stop_bg() {
    local name="$1" pidfile="$2"
    local pid=""
    [ -f "${pidfile}" ] && pid=$(cat "${pidfile}" 2>/dev/null)
    if [ -n "${pid}" ] && kill -0 "${pid}" 2>/dev/null; then
        kill "${pid}" 2>/dev/null || true
        local i
        for i in $(seq 1 "${CR_STOP_WAIT_RETRIES}"); do
            kill -0 "${pid}" 2>/dev/null || break
            sleep 1
        done
        if kill -0 "${pid}" 2>/dev/null; then
            warning "${name} did not exit on SIGTERM, sending SIGKILL"
            kill -9 "${pid}" 2>/dev/null || true
        fi
        success "${name} stopped (pid ${pid})"
    else
        local raw router_pid
        raw=$(cat "${CR_HOME}/data/router.pid" 2>/dev/null || true)
        router_pid="${raw%%:*}"
        if [ -n "${router_pid}" ] && kill -0 "${router_pid}" 2>/dev/null; then
            kill "${router_pid}" 2>/dev/null || true
            success "${name} stopped (router.pid ${router_pid})"
        else
            warning "${name} not running"
        fi
    fi
    rm -f "${pidfile}"
}

_cr_write_default_config() {
    local admin_ip="${CR_ADMIN_IP:-}"
    if [ -z "${admin_ip}" ]; then
        admin_ip="$(_cr_docker_bridge_ip)"
    fi
    admin_ip="${admin_ip:-127.0.0.1}"
    cat > "${CR_HOME}/config.yaml" <<EOF
# credential-router minimal config (generated by deploy module).
# Schema mirrors source repo's config.example.yaml; binary defaults cover
# everything else. Paths are relative — the systemd unit's
# WorkingDirectory=${CR_HOME} resolves them.
# admin.addr defaults to docker0 bridge IP (auto-detected at install) so
# other Docker containers on this host can reach admin API. Override
# with CR_ADMIN_IP env var (e.g., 127.0.0.1 to restore loopback).
server:
  bind_address: 127.0.0.1:${CR_PROXY_PORT}

admin:
  addr: ${admin_ip}:${CR_ADMIN_PORT}

data_dir: ./data
backup_dir: ./data/backups
EOF
    info "Wrote default config: ${CR_HOME}/config.yaml (admin: ${admin_ip}:${CR_ADMIN_PORT})"
}

# ===== 写 systemd unit（含 WorkingDirectory，保证 ./data ./secrets 相对路径正确解析）=====
_cr_write_systemd_unit() {
    local bin config
    bin=$(_cr_find_bin) || error "credential-router binary not found"
    config=$(_cr_find_config) || error "credential-router config not found"
    cat > "${CR_UNIT}" <<EOF
[Unit]
Description=Credential Router
After=network-online.target docker.service
Wants=network-online.target docker.service

[Service]
Type=simple
WorkingDirectory=${CR_HOME}
ExecStart=${bin} -config ${config}
Restart=on-failure
RestartSec=2s

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload 2>/dev/null || true
    info "Wrote ${CR_UNIT}"
}

# ===== install: 从 AGENTOS_ROOT 取构建产物 + 生成 config/secrets + systemd unit =====
credential_router_install() {
    local bin
    bin=$(_cr_find_bin) || error "credential-router binary not found: tried \${AGENTOS_ROOT}/credential-router_linux_* and \${CR_HOME}/dist/bin/credential-router"

    mkdir -p "${CR_HOME}/dist/bin"
    if [ ! -x "${CR_HOME}/dist/bin/credential-router" ]; then
        cp -f "${bin}" "${CR_HOME}/dist/bin/credential-router"
        chmod 755 "${CR_HOME}/dist/bin/credential-router"
        success "credential-router binary installed: ${CR_HOME}/dist/bin/credential-router"
    else
        info "credential-router already installed at ${CR_HOME}/dist/bin/credential-router"
    fi

    mkdir -p "${CR_HOME}"
    if [ ! -f "${CR_HOME}/config.yaml" ]; then
        _cr_write_default_config
    fi

    mkdir -p "${CR_HOME}/data" "${CR_HOME}/data/backups"

    if _cr_has_systemd; then
        _cr_write_systemd_unit
        systemctl enable "${CR_SVC}" \
            || error "Failed to enable credential-router units"
    fi

    success "credential-router installed (deploy dir: ${CR_HOME})"
}

# ===== up: 启动服务（systemd 或 nohup）+ 双端点健康检查 =====
credential_router_up() {
    local bin config
    bin=$(_cr_find_bin) || error "credential-router binary not found; run 'install' first"
    config=$(_cr_find_config) || error "credential-router config not found; run 'install' first"

    command -v curl >/dev/null 2>&1 || error "curl not found (required for health check)"

    if _cr_has_systemd; then
        if systemctl is-active --quiet "${CR_SVC}"; then
            warning "credential-router already running; run 'down' first to restart"
            return 0
        fi
        systemctl cat "${CR_SVC}" >/dev/null 2>&1 || error "credential-router.service not found; run 'install' first"
        systemctl enable --now "${CR_SVC}" || error "Failed to start ${CR_SVC}"
        if _cr_wait_healthy; then
            success "credential-router up (proxy :$(_cr_config_port bind_address "${CR_PROXY_PORT}"), admin :$(_cr_config_port addr "${CR_ADMIN_PORT}"))"
        else
            error "credential-router not healthy in ${CR_HEALTH_RETRIES}s, see: journalctl -u ${CR_SVC}"
        fi
    else
        if [ -f "${CR_PID_FILE}" ] && kill -0 "$(cat "${CR_PID_FILE}" 2>/dev/null)" 2>/dev/null; then
            warning "credential-router already running; run 'down' first to restart"
            return 0
        fi
        mkdir -p "${CR_RUN_DIR}" "${CR_LOG_DIR}"
        # 在部署根目录下启动，保证 config 中 ./data ./secrets 相对路径正确解析
        ( cd "${CR_HOME}" && _cr_start_bg credential-router "${CR_PID_FILE}" "${CR_LOG}" "${bin}" -config "${config}" )
        if _cr_wait_healthy; then
            success "credential-router up (proxy :$(_cr_config_port bind_address "${CR_PROXY_PORT}"), admin :$(_cr_config_port addr "${CR_ADMIN_PORT}"))"
        else
            error "credential-router not healthy in ${CR_HEALTH_RETRIES}s, see: ${CR_LOG}"
        fi
    fi
}

# ===== down: 停止服务（不禁用开机自启动）=====
credential_router_down() {
    if _cr_has_systemd; then
        systemctl stop "${CR_SVC}" 2>/dev/null \
            && success "credential-router stopped" || warning "credential-router not running"
    else
        _cr_stop_bg credential-router "${CR_PID_FILE}" credential-router || true
        success "credential-router stopped"
    fi
}

# ===== uninstall: 停服务 + 清理 unit/运行时目录 + 备份并移除持久化部署目录 =====
credential_router_uninstall() {
    if _cr_has_systemd; then
        systemctl disable --now "${CR_SVC}" 2>/dev/null || true
        rm -rf "${CR_UNIT}"
        systemctl daemon-reload 2>/dev/null || true
    else
        _cr_stop_bg credential-router "${CR_PID_FILE}" credential-router || true
        rm -rf "${CR_RUN_DIR}" "${CR_LOG_DIR}"
    fi

    # secrets/data 含密钥材料，卸载前备份到时间戳目录而非直接删除
    if [ -d "${CR_HOME}" ]; then
        local backup_dir="${CR_HOME}.bak-$(date +%Y%m%d-%H%M%S)"
        mv "${CR_HOME}" "${backup_dir}"
        info "Backed up credential-router deploy dir to ${backup_dir} (contains secrets/data)"
    fi

    success "credential-router uninstalled"
}

# ===== CLI 入口（对齐 jiuwenbox/module.sh: bash module.sh up/down/...）=====
# 当以脚本而非 source 方式执行时（bash module.sh up），走主入口；source
# 加载时（如 agentos.sh 引入）只定义函数不执行 case 分支。
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    case "${1:-}" in
        up)        credential_router_up ;;
        down)      credential_router_down ;;
        install)   credential_router_install ;;
        uninstall) credential_router_uninstall ;;
        status)
            if _cr_has_systemd && systemctl is-active --quiet "${CR_SVC}"; then
                echo "credential-router active (systemd)"
            elif [ -f "${CR_PID_FILE}" ] && kill -0 "$(cat "${CR_PID_FILE}" 2>/dev/null)" 2>/dev/null; then
                echo "credential-router running (pid $(cat "${CR_PID_FILE}"), nohup)"
            else
                echo "credential-router not running" >&2
                exit 1
            fi
            ;;
        *)
            echo "usage: $0 {up|down|install|uninstall|status}" >&2
            exit 2
            ;;
    esac
fi
