#!/usr/bin/env bash
set -euo >/dev/null 2>&1

# ============================================================
# agentos-etcd 独立启停脚本
#
# 从 yuanrong/module.sh 的 etcd 逻辑中拆出，单独管理 etcd unit 生命周期。
#   - 仅 etcd_nodes 节点生成并启动 agentos-etcd.service
#   - 角色推导读取 ~/.agentos/deploy/config.yaml（由 deploy/scripts/config.py 解析）
#   - etcd 二进制路径从 yr config dump 的 values.etcd.bin_path 探测，回退 yr 包内 third_party/etcd/etcd
#
# 用法:
#   ./etcd.sh up      # 生成并启动 etcd unit（非 etcd 节点跳过）
#   ./etcd.sh down    # 停止并删除 etcd unit（保留 /var/lib/agentos/etcd 数据）
#   ./etcd.sh check   # 探测 etcd 集群是否可达（供 agentos.sh up 前置检查）
#   ./etcd.sh clean   # 清理 etcd 数据（危险操作，需交互确认）
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

YR_PYTHON_VERSION="${YR_PYTHON_VERSION:-3.11}"
YR_CONFIG_PY="${SCRIPT_DIR}/scripts/config.py"
YR_ETCD_SVC="agentos-etcd"
YR_ETCD_UNIT="/etc/systemd/system/${YR_ETCD_SVC}.service"
YR_ETCD_DATA_DIR="/var/lib/agentos/etcd"
YR_ETCD_CLIENT_PORT="${YR_ETCD_CLIENT_PORT:-32379}"
YR_HEALTH_CHECK_RETRIES="${YR_HEALTH_CHECK_RETRIES:-30}"

# ===== 日志函数 =====
info()    { echo -e "\033[36m=== $@ ===\033[0m"; }
success() { echo -e "\033[32m✅ $@\033[0m"; }
warning() { echo -e "\033[33m⚠️  $@\033[0m"; }
error()   { echo -e "\033[31m❌ $@\033[0m"; exit 1; }

# ===== 检测 systemd 是否可用 =====
_yr_has_systemd() {
    command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]
}

# ===== 定位 python 解释器 =====
_yr_python() {
    command -v "python${YR_PYTHON_VERSION}" 2>/dev/null || command -v python3 2>/dev/null \
        || error "python not found (need python${YR_PYTHON_VERSION} or python3)"
}

# ===== config.py 封装：角色推导 =====
_yr_cfg() {
    "$(_yr_python)" "${YR_CONFIG_PY}" "$@"
}

# ===== 探测 yr 内置 etcd 二进制路径 =====
# 优先从 `yr config dump` 的 values.etcd.bin_path 读取；失败则回退到 yr 包内 third_party 路径。
_yr_etcd_bin_path() {
    local bin_path yr_pkg

    if command -v yr >/dev/null 2>&1; then
        bin_path=$(yr config dump 2>/dev/null \
            | grep -E "bin_path" \
            | grep -i "etcd" \
            | head -n1 \
            | sed -E 's/.*bin_path[[:space:]]*[:=][[:space:]]*"?([^",}]+)"?.*/\1/' \
            | tr -d '[:space:]')
        if [ -n "${bin_path}" ] && [ -x "${bin_path}" ]; then
            echo "${bin_path}"
            return 0
        fi
    fi

    yr_pkg=$("$(_yr_python)" -c "import yr, os; print(os.path.dirname(yr.__file__))" 2>/dev/null)
    if [ -n "${yr_pkg}" ] && [ -x "${yr_pkg}/third_party/etcd/etcd" ]; then
        echo "${yr_pkg}/third_party/etcd/etcd"
        return 0
    fi

    return 1
}

# ===== 生成 etcd unit（仅 etcd_nodes 节点调用） =====
# advertise IP 必须用本机在 etcd_nodes 中匹配到的 config IP（通配匹配时用通配 IP 本身），
# 不能用 get_local_ip 的真实 IP，否则 advertise 地址与 initial-cluster 不一致导致 bootstrap 失败。
_yr_generate_etcd_unit() {
    local etcd_bin node_name initial_cluster advertise_ip
    etcd_bin=$(_yr_etcd_bin_path) \
        || error "Cannot locate yr built-in etcd binary (yr config dump / third_party/etcd/etcd)"
    node_name=$(_yr_cfg etcd-name) || error "Failed to derive etcd node name"
    initial_cluster=$(_yr_cfg initial-cluster) || error "Failed to build initial-cluster"
    advertise_ip=$(_yr_cfg etcd-advertise-ip) \
        || error "Failed to derive etcd advertise IP"

    info "etcd unit: bin=${etcd_bin}, name=${node_name}, advertise=${advertise_ip}"

    cat > "${YR_ETCD_UNIT}" <<EOF
[Unit]
Description=AgentOS etcd Service
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
ExecStart=${etcd_bin} \\
    --name ${node_name} \\
    --data-dir ${YR_ETCD_DATA_DIR} \\
    --unsafe-no-fsync=false \\
    --auto-compaction-mode=revision \\
    --auto-compaction-retention=100000 \\
    --quota-backend-bytes=8589934592 \\
    --snapshot-count=10000 \\
    --heartbeat-interval=250 \\
    --election-timeout=2500 \\
    --pre-vote=true \\
    --strict-reconfig-check=true \\
    --listen-client-urls http://0.0.0.0:32379 \\
    --advertise-client-urls http://${advertise_ip}:32379 \\
    --listen-peer-urls http://0.0.0.0:32380 \\
    --initial-advertise-peer-urls http://${advertise_ip}:32380 \\
    --initial-cluster ${initial_cluster} \\
    --initial-cluster-state new \\
    --initial-cluster-token etcd-cluster-1
Restart=on-failure
RestartSec=5s
TimeoutStartSec=0
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF
}

# ===== up: 角色推导 → 生成 unit → enable --now → 健康检查 =====
# 历史数据问题由 down 自动清理保证（参考 yr stop 的行为）：
#   - etcd.sh down 自动清 /var/lib/agentos/etcd 数据
#   - agentos.sh init 在 up 前先 clean --yes
# 因此 up 不再做配置一致性检查，避免交互打断部署流程。
etcd_up() {
    [ -f "${YR_CONFIG_PY}" ] || error "config parser not found: ${YR_CONFIG_PY}"
    _yr_has_systemd || error "systemd not available; etcd.sh requires systemd"

    if ! _yr_cfg is-etcd-node; then
        info "This host is NOT an etcd node, skipping ${YR_ETCD_SVC}"
        return 0
    fi

    info "This host is an etcd node, generating ${YR_ETCD_SVC} unit"
    mkdir -p "${YR_ETCD_DATA_DIR}"

    _yr_generate_etcd_unit
    systemctl daemon-reload
    systemctl enable --now "${YR_ETCD_SVC}" || error "Failed to start ${YR_ETCD_SVC}"

    local i
    for i in $(seq 1 "${YR_HEALTH_CHECK_RETRIES}"); do
        systemctl is-active --quiet "${YR_ETCD_SVC}" && break
        sleep 1
    done
    systemctl is-active --quiet "${YR_ETCD_SVC}" \
        || error "${YR_ETCD_SVC} not active, see: journalctl -u ${YR_ETCD_SVC}"
    success "${YR_ETCD_SVC} up"
}

# ===== down: disable → 删除 unit（保留 /var/lib/agentos/etcd 数据） =====
# down 只停服务、删 unit，保留数据，便于 restart 反复使用。
# 清数据走 init（自动 clean）或 ./etcd.sh clean（手动）。
etcd_down() {
    _yr_has_systemd || { warning "systemd not available, nothing to stop"; return 0; }

    systemctl disable --now "${YR_ETCD_SVC}" 2>/dev/null || true
    rm -f "${YR_ETCD_UNIT}"
    systemctl daemon-reload
    success "${YR_ETCD_SVC} down (data preserved at ${YR_ETCD_DATA_DIR})"
}

# ===== clean: 清理 etcd 数据（默认直接清理，无需交互确认） =====
# 对齐 yr start 的语义：yr start 默认每次用全新 timestamped deploy_path，
# etcd 数据目录天然是空的，所以从不需要担心历史数据。
# agentos 用固定 /var/lib/agentos/etcd，没有时间戳隔离，故 clean 提供等价效果：
# 清空数据目录，下次 up 即视为干净 bootstrap。
# 默认 yes 直接清理；-y/--yes 为兼容别名（无实际作用）。
etcd_clean() {
    while [ $# -gt 0 ]; do
        case "$1" in
            -y|--yes) shift ;;  # 兼容别名，默认就是 yes
            -h|--help)
                cat << EOF
Usage: ./$(basename "$0") clean [-y|--yes]
  默认直接清理 /var/lib/agentos/etcd 数据，无交互确认（对齐 yr start 行为）
  -y, --yes  兼容别名，无实际作用（默认即 yes）
EOF
                return 0
                ;;
            *) error "Unknown option for clean: $1" ;;
        esac
    done

    if [ ! -d "${YR_ETCD_DATA_DIR}" ]; then
        info "etcd data directory does not exist: ${YR_ETCD_DATA_DIR}"
        return 0
    fi

    info "Cleaning etcd data directory: ${YR_ETCD_DATA_DIR}"
    rm -rf "${YR_ETCD_DATA_DIR:?}"/*
    success "etcd data cleaned: ${YR_ETCD_DATA_DIR}"
}

# ===== check: 探测 etcd 集群是否可达（供 agentos.sh up 前置检查调用） =====
# 遍历 config 中所有 etcd_nodes，对 client port 做 TCP 连通探测。
# 只要有任一节点可达即视为集群就绪（quorum 由 etcd 自身保证，这里只验连通性）。
# 全部不可达返回 1，调用方据此提示用户先执行 init。
etcd_check() {
    [ -f "${YR_CONFIG_PY}" ] || error "config parser not found: ${YR_CONFIG_PY}"

    local nodes node
    nodes=$(_yr_cfg etcd-nodes) || error "Failed to read etcd_nodes from config"
    [ -n "${nodes}" ] || error "etcd_nodes is empty in config"

    for node in ${nodes}; do
        # bash /dev/tcp 探测：3s 超时，成功即返回
        if timeout 3 bash -c "exec 3<>/dev/tcp/${node}/${YR_ETCD_CLIENT_PORT}" 2>/dev/null; then
            info "etcd reachable at ${node}:${YR_ETCD_CLIENT_PORT}"
            return 0
        fi
    done

    warning "No etcd node reachable on port ${YR_ETCD_CLIENT_PORT} (checked: ${nodes})"
    return 1
}

print_help() {
    cat << EOF
Usage: ./$(basename "$0") <COMMAND>

agentos-etcd 独立启停脚本，从 yuanrong/module.sh 的 etcd 逻辑中拆出。

角色推导读取 ~/.agentos/deploy/config.yaml：
  - 仅 etcd_nodes 节点生成并启动 agentos-etcd.service
  - etcd 二进制路径从 yr config dump 探测，回退 yr 包内 third_party/etcd/etcd

Commands:
  up      生成并启动 agentos-etcd.service（非 etcd 节点跳过）
          历史数据由 init 自动清理（clean + up），up 不做一致性检查
  down    停止并删除 agentos-etcd.service（保留 /var/lib/agentos/etcd 数据）
          便于 restart 反复使用；清数据走 init 或 clean
  check   探测 etcd 集群是否可达（TCP 连通任一 etcd_node 的 client port 即通过）
          供 agentos.sh up 前置检查调用；可达返回 0，全部不可达返回 1
  clean   清理 etcd 数据目录（默认直接清理，无交互确认）
          对齐 yr start 语义：每次 bootstrap 视为干净启动
          适用场景：不执行 down 就地重新 bootstrap；agentos.sh init 自动调用

Environment:
  YR_PYTHON_VERSION          Python 版本（默认 3.11）
  YR_HEALTH_CHECK_RETRIES    up 健康检查重试次数（默认 30，每次 1s）

Examples:
  # 修改 config.yaml 中的 etcd_nodes 后，清理数据并重新启动
  ./etcd.sh down
  ./etcd.sh clean
  ./etcd.sh up
EOF
    exit 0
}

main() {
    if [ $# -eq 0 ]; then
        print_help
    fi

    local cmd="$1"
    shift
    case "${cmd}" in
        up)        etcd_up "$@" ;;
        down)      etcd_down "$@" ;;
        check)     etcd_check "$@" ;;
        clean)     etcd_clean "$@" ;;
        -h|--help) print_help ;;
        *)         error "Unknown command: ${cmd} (use 'up', 'down', 'check', or 'clean')" ;;
    esac
}

main "$@"
