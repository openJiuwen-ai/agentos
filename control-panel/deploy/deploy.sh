#!/bin/bash
set -e

# 防止被 sh 执行（sh 不支持数组等 bash 特性）
if [ -z "$BASH_VERSION" ]; then
    echo "[agentos] 请用 bash 执行：bash $0 $*" >&2
    exec bash "$0" "$@"
fi

# ============================================================================
# AgentOS 一体机 部署脚本
#
# 用法:
#   sudo bash deploy.sh install     # 安装：.env + 镜像拉取 + node/npu_exporter 注册
#   sudo bash deploy.sh uninstall   # 卸载：反向清理
#   sudo bash deploy.sh up          # 启动：node/npu_exporter → docker compose
#   sudo bash deploy.sh down        # 停止：docker compose → node/npu_exporter（反序）
#   sudo bash deploy.sh restart     # 重启：down → up
#   sudo bash deploy.sh status      # 查看服务状态
# ============================================================================

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
NE_DIR="${DEPLOY_DIR}/node-exporter"
NPU_DIR="${DEPLOY_DIR}/npu-exporter"
SERVICE_NAME="node_exporter"
NPU_SERVICE="npu-exporter"
NPU_TIMER="npu-exporter.timer"
NE_BINARY="/usr/bin/node_exporter"
NPU_BINARY="/usr/local/bin/npu-exporter"
NPU_RUN_USER="hwMindX"
NPU_RUN_GROUP="hwMindX"

# ── 工具函数 ────────────────────────────────────────────────────────────────

log()  { echo "[agentos] $*"; }
fail() { echo "[agentos] ERROR: $*" >&2; exit 1; }

# 转义 sed 替换字符串中的特殊字符：\ & / |
sed_escape() {
    printf '%s' "$1" | sed 's/[\\&/|]/\\&/g'
}

# 加载 .env 到当前 shell（init_env 之后调用）
load_env() {
    local env_file="${DEPLOY_DIR}/.env"
    [ -f "$env_file" ] || return
    set -a
    # shellcheck disable=SC1090
    source <(tr -d '\r' < "$env_file")
    set +a
}

# 从 .env 读取的变量提供默认值
env_default() {
    local var="$1" default="$2"
    local val="${!var}"
    printf '%s' "${val:-$default}"
}

need_root() {
    [ "$(id -u)" -eq 0 ] || fail "需要 root 权限。请用: sudo bash $0 $ACTION"
}

# ── .env 初始化 ─────────────────────────────────────────────────────────────

init_env() {
    local env_file="${DEPLOY_DIR}/.env"
    local env_example="${DEPLOY_DIR}/.env.example"

    if [ -f "$env_file" ]; then
        log ".env 已存在，跳过。"
        return
    fi
    [ -f "$env_example" ] || fail ".env.example 不存在"

    cp "$env_example" "$env_file"

    read -rp "POSTGRES_USER [agentos]: " val
    sed -i "s/^POSTGRES_USER=.*/POSTGRES_USER=$(sed_escape "${val:-agentos}")/" "$env_file"

    read -rsp "POSTGRES_PASSWORD: " val; echo
    [ -n "$val" ] || fail "POSTGRES_PASSWORD 不能为空"
    sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(sed_escape "$val")/" "$env_file"

    read -rp "AGENTOS_ADMIN_USERNAME [admin]: " val
    sed -i "s/^AGENTOS_ADMIN_USERNAME=.*/AGENTOS_ADMIN_USERNAME=$(sed_escape "${val:-admin}")/" "$env_file"

    read -rsp "AGENTOS_ADMIN_PASSWORD: " val; echo
    [ -n "$val" ] || fail "AGENTOS_ADMIN_PASSWORD 不能为空"
    sed -i "s/^AGENTOS_ADMIN_PASSWORD=.*/AGENTOS_ADMIN_PASSWORD=$(sed_escape "$val")/" "$env_file"

    local jwt_key llm_enc
    jwt_key=$(openssl rand -hex 32 2>/dev/null || head -c 64 /dev/urandom | od -An -tx1 | tr -d ' \n' | head -c 64)
    sed -i "s/^AGENTOS_JWT_SECRET_KEY=.*/AGENTOS_JWT_SECRET_KEY=${jwt_key}/" "$env_file"

    read -rp "LITELLM_MASTER_KEY (sk- 开头，留空自动生成): " val
    if [ -z "$val" ]; then
        val="sk-$(openssl rand -hex 24 2>/dev/null || head -c 48 /dev/urandom | od -An -tx1 | tr -d ' \n' | head -c 48)"
        log "  自动生成: $val"
    fi
    sed -i "s/^LITELLM_MASTER_KEY=.*/LITELLM_MASTER_KEY=$(sed_escape "$val")/" "$env_file"

    llm_enc=$(openssl rand -hex 32 2>/dev/null || head -c 64 /dev/urandom | od -An -tx1 | tr -d ' \n' | head -c 64)
    sed -i "s/^LITELLM_KEY_ENCRYPTION_KEY=.*/LITELLM_KEY_ENCRYPTION_KEY=${llm_enc}/" "$env_file"

    # ── LiteLLM / Exporter 主机 IP ──
    echo ""
    log "  以下 HOST 需要填入本机可访问的 IP 地址"
    log "  （后端通过此地址访问各服务，localhost 仅限本机访问）"
    echo ""

    read -rp "LITELLM_HOST [localhost]: " val
    sed -i "s/^LITELLM_HOST=.*/LITELLM_HOST=$(sed_escape "${val:-localhost}")/" "$env_file"
    log "  LITELLM_HOST = ${val:-localhost}"

    read -rp "NODE_EXPORTER_HOST [127.0.0.1]: " val
    sed -i "s/^NODE_EXPORTER_HOST=.*/NODE_EXPORTER_HOST=$(sed_escape "${val:-127.0.0.1}")/" "$env_file"
    log "  NODE_EXPORTER_HOST = ${val:-127.0.0.1}"

    read -rp "NPU_EXPORTER_HOST [127.0.0.1]: " val
    sed -i "s/^NPU_EXPORTER_HOST=.*/NPU_EXPORTER_HOST=$(sed_escape "${val:-127.0.0.1}")/" "$env_file"
    log "  NPU_EXPORTER_HOST = ${val:-127.0.0.1}"

    # ── 注册中心（选填）──
    echo ""
    log "  注册中心 (AGENT_REGISTER_URL) 用于智能体监控功能"
    log "  同机部署示例: http://host.docker.internal:8000"
    log "  远程部署示例: http://192.168.0.20:8000"
    log "  留空则管理面正常启动，仅\"智能体监控\"功能不可用"
    read -rp "AGENT_REGISTER_URL [留空禁用]: " val
    if [ -n "$val" ]; then
        sed -i "s|^AGENT_REGISTER_URL=.*|AGENT_REGISTER_URL=$(sed_escape "$val")|" "$env_file"
        log "  AGENT_REGISTER_URL = ${val}"
    else
        log "  AGENT_REGISTER_URL = (已禁用)"
    fi

    # ── 自动检测硬件信息 ──
    local host_name product_name
    host_name=$(hostname 2>/dev/null || echo "")
    if [ -n "$host_name" ]; then
        sed -i "s/^AGENTOS_HOSTNAME=.*/AGENTOS_HOSTNAME=\"$(sed_escape "$host_name")\"/" "$env_file"
        log "  AGENTOS_HOSTNAME = ${host_name}"
    fi

    product_name=$(dmidecode -s system-product-name 2>/dev/null || echo "")
    if [ -n "$product_name" ]; then
        sed -i "s/^AGENTOS_PRODUCT_NAME=.*/AGENTOS_PRODUCT_NAME=\"$(sed_escape "$product_name")\"/" "$env_file"
        log "  AGENTOS_PRODUCT_NAME = ${product_name}"
    fi

    echo ""
    log ".env 已生成。"
}

# ── 镜像检测与拉取 ─────────────────────────────────────────────────────────

pull_images() {
    cd "$DEPLOY_DIR"
    log "检测/拉取 Docker 镜像 ..."

    local missing=()
    local extracted=""
    # 从 docker-compose.yml 提取所有 service 的镜像名，逐个检测
    while IFS= read -r img; do
        [ -z "$img" ] && continue
        extracted="yes"
        if docker image inspect "$img" &>/dev/null; then
            log "  $img — 本地已存在"
        else
            log "  $img — 不存在，需要拉取"
            missing+=("$img")
        fi
    done < <(docker compose config --format json 2>/dev/null \
        | python3 -c "
import sys, json
data = json.load(sys.stdin)
for svc in data.get('services', {}).values():
    img = svc.get('image', '')
    if img:
        print(img)
" 2>/dev/null)

    # Fallback: 如果 docker compose config 或 python3 不可用，逐个检测已知镜像
    if [ -z "$extracted" ]; then
        local fallback_images=(
            "agentos-control-panel:latest"
            "postgres:18.0"
            "ghcr.io/berriai/litellm-database:v1.91.1"
            "victoriametrics/victoria-metrics:v1.135.0"
            "grafana/grafana:12.4.2"
        )
        for img in "${fallback_images[@]}"; do
            if ! docker image inspect "$img" &>/dev/null; then
                log "  $img — 不存在，需要拉取"
                missing+=("$img")
            fi
        done
    fi

    if [ ${#missing[@]} -eq 0 ]; then
        log "所有镜像已就绪。"
        return
    fi

    # 只拉取本地缺失的镜像（按 service 逐个拉）
    for img in "${missing[@]}"; do
        # agentos-control-panel 是本地构建的，尝试从 compose 拉取失败时给提示
        if [[ "$img" == agentos-control-panel:* ]]; then
            docker compose pull agentos 2>/dev/null || {
                log "  WARNING: $img 拉取失败，请先本地构建:"
                log "    cd control-panel && docker build -f image/Dockerfile -t agentos ."
            }
        else
            log "  拉取 $img ..."
            docker pull "$img" 2>/dev/null || log "  WARNING: $img 拉取失败"
        fi
    done

    log "镜像就绪。"
}

# ── node_exporter 安装/卸载 ────────────────────────────────────────────────

install_node_exporter() {
    local ne_port ne_host listen_addr
    ne_port=$(env_default NODE_EXPORTER_PORT 8084)
    ne_host=$(env_default NODE_EXPORTER_HOST 127.0.0.1)

    # 构建 listen address：host:port 或 :port（host 为空/0.0.0.0 时）
    if [ -z "$ne_host" ] || [ "$ne_host" = "0.0.0.0" ]; then
        listen_addr=":${ne_port}"
    else
        listen_addr="${ne_host}:${ne_port}"
    fi

    # 二进制由外部流程解压到 node-exporter/ 目录，install 负责拷贝到 /usr/bin
    local ne_bin="${NE_DIR}/node_exporter"
    if [ -f "$ne_bin" ]; then
        # 已有服务或二进制时，强制要求先 uninstall
        if systemctl is-active "$SERVICE_NAME" &>/dev/null \
           || systemctl is-enabled "$SERVICE_NAME" &>/dev/null \
           || [ -f "$NE_BINARY" ]; then
            fail "node_exporter 已安装，请先执行: sudo bash $0 uninstall"
        fi
        cp "$ne_bin" "$NE_BINARY"
        chmod +x "$NE_BINARY"
        log "  已拷贝 $NE_BINARY"
    elif [ ! -f "$NE_BINARY" ]; then
        fail "node_exporter 二进制不存在：$ne_bin 且 $NE_BINARY 未安装"
    else
        log "  $NE_BINARY 已存在，跳过拷贝"
    fi

    # 创建系统用户
    if id "$SERVICE_NAME" &>/dev/null; then
        log "  用户 '$SERVICE_NAME' 已存在"
    else
        useradd --no-create-home --shell /usr/sbin/nologin --system "$SERVICE_NAME"
        log "  已创建系统用户 '$SERVICE_NAME'"
    fi

    # 安装 systemd unit（从模板生成，替换监听地址）
    sed "s|__LISTEN_ADDR__|${listen_addr}|" \
        "${NE_DIR}/node_exporter.service" > /etc/systemd/system/${SERVICE_NAME}.service

    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    log "  systemd unit 已注册 (${listen_addr})"
}

uninstall_node_exporter() {
    if systemctl is-active "$SERVICE_NAME" &>/dev/null; then
        systemctl stop "$SERVICE_NAME"
    fi
    if systemctl is-enabled "$SERVICE_NAME" &>/dev/null; then
        systemctl disable "$SERVICE_NAME" 2>/dev/null
    fi
    if [ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]; then
        rm "/etc/systemd/system/${SERVICE_NAME}.service"
        systemctl daemon-reload
        log "  已移除 ${SERVICE_NAME}.service"
    fi
    if [ -f "$NE_BINARY" ]; then
        rm "$NE_BINARY"
        log "  已删除 $NE_BINARY"
    fi
}

# ── npu_exporter 安装/卸载 ─────────────────────────────────────────────

install_npu_exporter() {
    [ -d "$NPU_DIR" ] || fail "npu-exporter 目录不存在: $NPU_DIR"
    [ -f "${NPU_DIR}/npu-exporter" ] || fail "npu-exporter 二进制不存在: ${NPU_DIR}/npu-exporter"
    [ -f "${NPU_DIR}/npu-exporter.service" ] || fail "npu-exporter.service 不存在"
    [ -f "${NPU_DIR}/npu-exporter.timer" ] || fail "npu-exporter.timer 不存在"

    local npu_port npu_host listen_addr
    npu_port=$(env_default NPU_EXPORTER_PORT 8083)
    npu_host=$(env_default NPU_EXPORTER_HOST 127.0.0.1)

    # 创建运行用户
    if ! getent group "$NPU_RUN_GROUP" &>/dev/null; then
        groupadd -r "$NPU_RUN_GROUP" 2>/dev/null || groupadd "$NPU_RUN_GROUP"
        log "  已创建用户组 '$NPU_RUN_GROUP'"
    fi
    if ! id "$NPU_RUN_USER" &>/dev/null; then
        useradd -r -g "$NPU_RUN_GROUP" -s /sbin/nologin "$NPU_RUN_USER" 2>/dev/null \
            || useradd -g "$NPU_RUN_GROUP" -s /sbin/nologin "$NPU_RUN_USER"
        log "  已创建用户 '$NPU_RUN_USER'"
    fi

    # 安装二进制
    install -m 500 -o "$NPU_RUN_USER" -g "$NPU_RUN_GROUP" \
        "${NPU_DIR}/npu-exporter" "$NPU_BINARY"
    log "  已安装 $NPU_BINARY"

    # 安装配置文件
    local cfg
    for cfg in metricConfiguration.json pluginConfiguration.json; do
        if [ -f "${NPU_DIR}/${cfg}" ]; then
            cp -f "${NPU_DIR}/${cfg}" "/usr/local/${cfg}"
            log "  已安装 /usr/local/${cfg}"
        fi
    done

    # 安装 systemd unit（替换占位符）
    sed -e "s|__NPU_LISTEN_ADDR__|${npu_host}|g" \
        -e "s|__NPU_PORT__|${npu_port}|g" \
        "${NPU_DIR}/npu-exporter.service" > "/etc/systemd/system/${NPU_SERVICE}.service"
    cp -f "${NPU_DIR}/npu-exporter.timer" "/etc/systemd/system/${NPU_TIMER}"
    systemctl daemon-reload
    systemctl enable "$NPU_TIMER" "${NPU_SERVICE}.service"
    log "  systemd unit 已注册 (${npu_host}:${npu_port})"
}

uninstall_npu_exporter() {
    systemctl stop "$NPU_TIMER" 2>/dev/null || true
    systemctl stop "${NPU_SERVICE}.service" 2>/dev/null || true

    if systemctl is-enabled "$NPU_TIMER" &>/dev/null \
       || systemctl is-enabled "${NPU_SERVICE}.service" &>/dev/null; then
        systemctl disable "$NPU_TIMER" "${NPU_SERVICE}.service" 2>/dev/null || true
    fi

    if [ -f "/etc/systemd/system/${NPU_SERVICE}.service" ]; then
        rm "/etc/systemd/system/${NPU_SERVICE}.service"
        log "  已移除 ${NPU_SERVICE}.service"
    fi
    if [ -f "/etc/systemd/system/${NPU_TIMER}" ]; then
        rm "/etc/systemd/system/${NPU_TIMER}"
        log "  已移除 ${NPU_TIMER}"
    fi

    if [ -f "$NPU_BINARY" ]; then
        rm "$NPU_BINARY"
        log "  已删除 $NPU_BINARY"
    fi

    systemctl daemon-reload 2>/dev/null || true
}

# ── install ─────────────────────────────────────────────────────────────────

do_install() {
    need_root
    log "========== install =========="

    log "[1/4] 初始化 .env"
    init_env
    load_env

    local ne_port
    ne_port=$(env_default NODE_EXPORTER_PORT 8084)
    log "[2/4] 安装 node_exporter (port ${ne_port})"
    install_node_exporter

    log "[3/4] 安装 npu_exporter"
    if [ -d "$NPU_DIR" ]; then
        install_npu_exporter
    else
        log "  跳过：npu-exporter 目录不存在"
    fi

    log "[4/4] 拉取 Docker 镜像"
    pull_images

    log "install 完成。"
    echo ""
    log "提示: 如需修改端口等配置，可直接编辑 ${DEPLOY_DIR}/.env"
    log "执行 'sudo bash deploy.sh up' 启动服务。"
}

# ── uninstall ───────────────────────────────────────────────────────────────

do_uninstall() {
    need_root
    log "========== uninstall =========="

    log "[1/4] 停止 Docker 服务"
    cd "$DEPLOY_DIR"
    docker compose down -v || true

    log "[2/4] 注销 node_exporter"
    uninstall_node_exporter

    log "[3/4] 注销 npu_exporter"
    uninstall_npu_exporter

    log "[4/4] 清理 .env"
    if [ -f "${DEPLOY_DIR}/.env" ]; then
        if [ "$KEEP_ENV" -eq 1 ]; then
            log "  保留 .env"
        else
            rm "${DEPLOY_DIR}/.env"
            log "  已删除 .env（保留请用: sudo bash $0 uninstall --keep-env）"
        fi
    fi

    log "uninstall 完成。"
}

# ── up ──────────────────────────────────────────────────────────────────────

do_up() {
    need_root
    log "========== up =========="

    log "[1/3] 启动 node_exporter"
    if systemctl is-active "$SERVICE_NAME" &>/dev/null; then
        log "  node_exporter 已在运行"
    elif systemctl cat "$SERVICE_NAME" &>/dev/null; then
        systemctl start "$SERVICE_NAME"
        log "  node_exporter: started"
    else
        log "  WARNING: node_exporter 未安装，请先执行: sudo bash $0 install"
    fi
    systemctl is-active "$SERVICE_NAME" &>/dev/null \
        && log "  node_exporter: running" \
        || log "  WARNING: node_exporter 未运行"

    log "[2/3] 启动 npu_exporter"
    if systemctl cat "$NPU_SERVICE" &>/dev/null; then
        systemctl start "$NPU_SERVICE" 2>/dev/null || true
        systemctl start "$NPU_TIMER" 2>/dev/null || true
        systemctl is-active "$NPU_SERVICE" &>/dev/null \
            && log "  npu_exporter: running" \
            || log "  npu_exporter: timer will start on next boot"
    else
        log "  跳过：npu_exporter 未安装"
    fi

    log "[3/3] 启动 Docker 服务"
    cd "$DEPLOY_DIR"
    docker compose up -d

    do_status
}

# ── down ────────────────────────────────────────────────────────────────────

do_down() {
    need_root
    log "========== down =========="

    log "[1/3] 停止 Docker 服务"
    cd "$DEPLOY_DIR"
    docker compose stop

    log "[2/3] 停止 node_exporter"
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    log "  node_exporter: stopped"

    log "[3/3] 停止 npu_exporter"
    systemctl stop "$NPU_TIMER" 2>/dev/null || true
    systemctl stop "$NPU_SERVICE" 2>/dev/null || true
    log "  npu_exporter: stopped"

    log "down 完成。"
}

# ── restart ───────────────────────────────────────────────────────────

do_restart() {
    do_down
    do_up
}

# ── status ──────────────────────────────────────────────────────────────────

do_status() {
    load_env
    local ne_port npu_port grafana_port
    ne_port=$(env_default NODE_EXPORTER_PORT 8084)
    npu_port=$(env_default NPU_EXPORTER_PORT 8083)
    grafana_port=$(env_default GRAFANA_PORT 3000)

    echo ""
    log "--- docker compose ps ---"
    cd "$DEPLOY_DIR"
    docker compose ps 2>/dev/null

    echo ""
    log "--- 端口健康检查 ---"

    _check() {
        local name="$1" ok="$2"
        if [ "$ok" = "1" ]; then
            echo "  [OK]   ${name}"
        else
            echo "  [--]   ${name}"
        fi
    }

    curl -sf "http://127.0.0.1:${ne_port}/metrics" &>/dev/null \
        && _check "node_exporter    (:${ne_port})" 1 \
        || _check "node_exporter    (:${ne_port})" 0

    curl -sf "http://127.0.0.1:${npu_port}/metrics" &>/dev/null \
        && _check "npu_exporter     (:${npu_port})" 1 \
        || _check "npu_exporter     (:${npu_port})" 0

    curl -sfI "http://127.0.0.1:8080/" &>/dev/null \
        && _check "frontend         (:8080)" 1 \
        || _check "frontend         (:8080)" 0

    docker ps --filter "name=deploy-postgres-1" --format "{{.Status}}" 2>/dev/null | grep -qi healthy \
        && _check "postgres         (:5432)" 1 \
        || _check "postgres         (:5432)" 0

    curl -sf "http://127.0.0.1:4000/health/liveliness" 2>/dev/null | grep -qi alive \
        && _check "litellm          (:4000)" 1 \
        || _check "litellm          (:4000)" 0

    curl -sf "http://127.0.0.1:8428/health" 2>/dev/null | grep -qi ok \
        && _check "victoriametrics  (:8428)" 1 \
        || _check "victoriametrics  (:8428)" 0

    curl -sf "http://127.0.0.1:${grafana_port}/api/health" 2>/dev/null | grep -qi ok \
        && _check "grafana          (:${grafana_port})" 1 \
        || _check "grafana          (:${grafana_port})" 0

    unset -f _check
    echo ""
}

# ── 入口 ────────────────────────────────────────────────────────────────────

ACTION="${1:-help}"
KEEP_ENV=0
[ "${2:-}" = "--keep-env" ] && KEEP_ENV=1

case "$ACTION" in
    install)   do_install ;;
    uninstall) do_uninstall ;;
    up)        do_up ;;
    down)      do_down ;;
    restart)   do_restart ;;
    status)    do_status ;;
    *)
        echo "用法: sudo bash $0 {install|uninstall|up|down|restart|status} [--keep-env]"
        echo ""
        echo "  install   安装：.env + 镜像拉取 + node/npu_exporter 注册"
        echo "  uninstall 卸载：停止服务 + 注销 systemd + 删除 .env"
        echo "  up        启动：node/npu_exporter → docker compose"
        echo "  down      停止：docker compose → node/npu_exporter（反序）"
        echo "  restart   重启：down → up"
        echo "  status    查看服务状态"
        echo ""
        echo "  --keep-env  uninstall 时保留 .env"
        exit 1
        ;;
esac
