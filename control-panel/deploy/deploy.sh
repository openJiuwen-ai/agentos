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
#   sudo bash deploy.sh install              # 安装（非交互式，拷贝到 ~/.agentos/.agent-manager 后执行）
#   sudo bash deploy.sh install -i           # 安装（交互式，拷贝到 ~/.agentos/.agent-manager 后执行）
#   sudo bash deploy.sh uninstall            # 卸载（默认保留数据和 .env）
#   sudo bash deploy.sh uninstall --clean    # 卸载（删除数据卷和 .env）
#   sudo bash deploy.sh up                   # 启动：更新 exporter 配置 → 启动服务
#   sudo bash deploy.sh down                 # 停止：docker compose → node/npu_exporter（反序）
#   sudo bash deploy.sh restart              # 重启：down → up
#   sudo bash deploy.sh status               # 查看服务状态
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

# 生成安全随机十六进制字符串
rand_hex() {
    local len="${1:-32}"
    openssl rand -hex "$len" 2>/dev/null || head -c "$((len * 2))" /dev/urandom | od -An -tx1 | tr -d ' \n' | head -c "$((len * 2))"
}

# 校验 IPv4 地址格式
valid_ipv4() {
    local ip="$1"
    # 允许 localhost 和空值
    [ -z "$ip" ] || [ "$ip" = "localhost" ] && return 0
    # IPv4 格式校验：四组 0-255，点分十进制
    echo "$ip" | grep -qE '^([0-9]{1,3}\.){3}[0-9]{1,3}$' || return 1
    local IFS='.'
    read -ra octets <<< "$ip"
    for octet in "${octets[@]}"; do
        [ "$octet" -ge 0 ] && [ "$octet" -le 255 ] || return 1
    done
}

# 带校验的 IP 输入
read_ip() {
    local prompt="$1" default="$2" val
    while true; do
        read -rp "$prompt" val
        val="${val:-$default}"
        if valid_ipv4 "$val"; then
            echo "$val"
            return
        fi
        log "  ERROR: '$val' 不是有效的 IPv4 地址，请重新输入"
    done
}

# 获取本机 IP（默认路由的源地址）
detect_host_ip() {
    local ip_addr
    ip_addr=$(ip -o -4 route get 1 2>/dev/null | awk '{print $7}')
    [ -n "$ip_addr" ] && echo "$ip_addr" || echo "127.0.0.1"
}

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

    # 失败时清理不完整的 .env（fail 调用 exit 会触发此 trap）
    trap 'rm -f "'"$env_file"'"' EXIT

    if [ "$INTERACTIVE" -eq 1 ]; then
        _init_env_interactive "$env_file"
    else
        _init_env_noninteractive "$env_file"
    fi

    # 初始化成功，取消 trap
    trap - EXIT

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

# 非交互式：优先读取环境变量，未设置则自动生成/使用默认值
_init_env_noninteractive() {
    local env_file="$1"

    # 用户名/密码：优先读环境变量，未设置则用默认值/自动生成
    local pg_user="${POSTGRES_USER:-agentos}"
    local pg_pass="${POSTGRES_PASSWORD:-agentos123}"
    local admin_user="${AGENTOS_ADMIN_USERNAME:-admin}"
    local admin_pass="${AGENTOS_ADMIN_PASSWORD:-admin123}"

    # 密钥：始终自动生成（不从外部传入）
    local jwt_key llm_key llm_enc
    jwt_key=$(rand_hex 32)
    llm_key="sk-$(rand_hex 24)"
    llm_enc=$(rand_hex 32)

    # 主机地址：优先读环境变量，未设置则自动检测本机 IP
    local detected_ip
    detected_ip=$(detect_host_ip)
    local llm_host="${LITELLM_HOST:-$detected_ip}"
    local ne_host="${NODE_EXPORTER_HOST:-$detected_ip}"
    local npu_host="${NPU_EXPORTER_HOST:-$detected_ip}"
    local register_url="${AGENT_REGISTER_URL:-}"

    sed -i "s/^POSTGRES_USER=.*/POSTGRES_USER=$(sed_escape "$pg_user")/" "$env_file"
    sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(sed_escape "$pg_pass")/" "$env_file"
    sed -i "s/^AGENTOS_ADMIN_USERNAME=.*/AGENTOS_ADMIN_USERNAME=$(sed_escape "$admin_user")/" "$env_file"
    sed -i "s/^AGENTOS_ADMIN_PASSWORD=.*/AGENTOS_ADMIN_PASSWORD=$(sed_escape "$admin_pass")/" "$env_file"
    sed -i "s/^AGENTOS_JWT_SECRET_KEY=.*/AGENTOS_JWT_SECRET_KEY=${jwt_key}/" "$env_file"
    sed -i "s/^LITELLM_MASTER_KEY=.*/LITELLM_MASTER_KEY=$(sed_escape "$llm_key")/" "$env_file"
    sed -i "s/^LITELLM_KEY_ENCRYPTION_KEY=.*/LITELLM_KEY_ENCRYPTION_KEY=${llm_enc}/" "$env_file"
    sed -i "s/^LITELLM_HOST=.*/LITELLM_HOST=$(sed_escape "$llm_host")/" "$env_file"
    sed -i "s/^NODE_EXPORTER_HOST=.*/NODE_EXPORTER_HOST=$(sed_escape "$ne_host")/" "$env_file"
    sed -i "s/^NPU_EXPORTER_HOST=.*/NPU_EXPORTER_HOST=$(sed_escape "$npu_host")/" "$env_file"

    if [ -n "$register_url" ]; then
        sed -i "s|^AGENT_REGISTER_URL=.*|AGENT_REGISTER_URL=$(sed_escape "$register_url")|" "$env_file"
    fi

    log "  非交互模式："
    log "  POSTGRES_USER      = ${pg_user}"
    log "  POSTGRES_PASSWORD  = ${pg_pass}"
    log "  ADMIN_USERNAME     = ${admin_user}"
    log "  ADMIN_PASSWORD     = ${admin_pass}"
    log "  LITELLM_MASTER_KEY = ${llm_key}"
    log "  （JWT_KEY / LLM_ENC 已自动生成，可在 .env 中查看）"
    log "  LITELLM_HOST       = ${llm_host}"
    log "  NODE_EXPORTER_HOST = ${ne_host}"
    log "  NPU_EXPORTER_HOST  = ${npu_host}"
    log "  AGENT_REGISTER_URL = ${register_url:-（已禁用）}"
}

# 交互式：逐项询问用户
_init_env_interactive() {
    local env_file="$1" val

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
    jwt_key=$(rand_hex 32)
    sed -i "s/^AGENTOS_JWT_SECRET_KEY=.*/AGENTOS_JWT_SECRET_KEY=${jwt_key}/" "$env_file"

    read -rp "LITELLM_MASTER_KEY (sk- 开头，留空自动生成): " val
    if [ -z "$val" ]; then
        val="sk-$(rand_hex 24)"
        log "  自动生成: $val"
    fi
    sed -i "s/^LITELLM_MASTER_KEY=.*/LITELLM_MASTER_KEY=$(sed_escape "$val")/" "$env_file"

    llm_enc=$(rand_hex 32)
    sed -i "s/^LITELLM_KEY_ENCRYPTION_KEY=.*/LITELLM_KEY_ENCRYPTION_KEY=${llm_enc}/" "$env_file"

    # ── LiteLLM / Exporter 主机 IP ──
    echo ""
    log "  以下 HOST 需要填入本机可访问的 IP 地址"
    log "  （后端通过此地址访问各服务，留空则自动检测本机 IP）"
    echo ""

    local detected_ip
    detected_ip=$(detect_host_ip)

    val=$(read_ip "LITELLM_HOST [${detected_ip}]: " "$detected_ip")
    sed -i "s/^LITELLM_HOST=.*/LITELLM_HOST=$(sed_escape "$val")/" "$env_file"
    log "  LITELLM_HOST = ${val}"

    val=$(read_ip "NODE_EXPORTER_HOST [${detected_ip}]: " "$detected_ip")
    sed -i "s/^NODE_EXPORTER_HOST=.*/NODE_EXPORTER_HOST=$(sed_escape "$val")/" "$env_file"
    log "  NODE_EXPORTER_HOST = ${val}"

    val=$(read_ip "NPU_EXPORTER_HOST [${detected_ip}]: " "$detected_ip")
    sed -i "s/^NPU_EXPORTER_HOST=.*/NPU_EXPORTER_HOST=$(sed_escape "$val")/" "$env_file"
    log "  NPU_EXPORTER_HOST = ${val}"

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
            "agentos-image-process:latest"
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

    # Agent 基础镜像（image-process 构建依赖，不由 compose 管理）
    if docker image inspect "agent-base:1.0" &>/dev/null; then
        log "  agent-base:1.0 — 本地已存在"
    else
        log "  WARNING: 缺少 agent-base:1.0，请先 docker load 到本机"
    fi

    if [ ${#missing[@]} -eq 0 ]; then
        log "所有镜像已就绪。"
        return
    fi

    # 只拉取本地缺失的镜像（按 service 逐个拉）
    for img in "${missing[@]}"; do
        if [[ "$img" == agentos-control-panel:* ]]; then
            docker compose pull agentos 2>/dev/null || {
                log "  WARNING: $img 拉取失败，请先本地构建:"
                log "    cd control-panel && docker build -f image/Dockerfile -t agentos ."
            }
        elif [[ "$img" == agentos-image-process:* ]]; then
            docker compose pull image-process 2>/dev/null || {
                log "  WARNING: $img 拉取失败，请先推送至仓库或 docker load 导入本机"
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

    # 检查二进制是否存在
    local ne_bin="${NE_DIR}/node_exporter"
    if [ ! -f "$ne_bin" ] && [ ! -f "$NE_BINARY" ]; then
        log "  WARNING: node_exporter 二进制不存在（${ne_bin} 和 ${NE_BINARY} 均不存在），跳过安装"
        return 1
    fi

    # 构建 listen address：host:port 或 :port（host 为空/0.0.0.0 时）
    if [ -z "$ne_host" ] || [ "$ne_host" = "0.0.0.0" ]; then
        listen_addr=":${ne_port}"
    else
        listen_addr="${ne_host}:${ne_port}"
    fi

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
    if ! systemctl cat "$SERVICE_NAME" &>/dev/null && [ ! -f "$NE_BINARY" ]; then
        log "  跳过：node_exporter 未安装"
        return
    fi
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
    local missing=()
    [ -d "$NPU_DIR" ] || missing+=("目录 ${NPU_DIR}")
    [ -f "${NPU_DIR}/npu-exporter" ] || missing+=("二进制 ${NPU_DIR}/npu-exporter")
    [ -f "${NPU_DIR}/npu-exporter.service" ] || missing+=("service ${NPU_DIR}/npu-exporter.service")
    [ -f "${NPU_DIR}/npu-exporter.timer" ] || missing+=("timer ${NPU_DIR}/npu-exporter.timer")

    if [ ${#missing[@]} -gt 0 ]; then
        log "  WARNING: npu-exporter 缺少文件，跳过安装："
        for item in "${missing[@]}"; do
            log "    - ${item}"
        done
        return 1
    fi

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
    if ! systemctl cat "$NPU_SERVICE" &>/dev/null && [ ! -f "$NPU_BINARY" ]; then
        log "  跳过：npu-exporter 未安装"
        return
    fi

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

    log "[2/4] 安装 node_exporter"
    install_node_exporter || true

    log "[3/4] 安装 npu_exporter"
    install_npu_exporter || true

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

    log "[1/3] 停止 Docker 服务"
    cd "$DEPLOY_DIR"
    if [ "$CLEAN" -eq 1 ]; then
        docker compose down -v || true
        log "  已停止并删除数据卷"
    else
        docker compose down || true
        log "  已停止（数据卷保留）"
    fi

    log "[2/3] 注销 node_exporter"
    uninstall_node_exporter

    log "[3/3] 注销 npu_exporter"
    uninstall_npu_exporter

    if [ "$CLEAN" -eq 1 ] && [ -f "${DEPLOY_DIR}/.env" ]; then
        rm "${DEPLOY_DIR}/.env"
        log "  已删除 .env"
    fi

    log "uninstall 完成。"
}

# ── 更新 exporter 服务配置 ──────────────────────────────────────────────

update_exporter_configs() {
    load_env

    local ne_port ne_host ne_listen
    ne_port=$(env_default NODE_EXPORTER_PORT 8084)
    ne_host=$(env_default NODE_EXPORTER_HOST 127.0.0.1)
    if [ -z "$ne_host" ] || [ "$ne_host" = "0.0.0.0" ]; then
        ne_listen=":${ne_port}"
    else
        ne_listen="${ne_host}:${ne_port}"
    fi

    if [ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]; then
        sed "s|__LISTEN_ADDR__|${ne_listen}|" \
            "${NE_DIR}/node_exporter.service" > /etc/systemd/system/${SERVICE_NAME}.service
        systemctl daemon-reload
        log "  node_exporter 配置已更新 (${ne_listen})"
    fi

    local npu_port npu_host
    npu_port=$(env_default NPU_EXPORTER_PORT 8083)
    npu_host=$(env_default NPU_EXPORTER_HOST 127.0.0.1)

    if [ -f "/etc/systemd/system/${NPU_SERVICE}.service" ]; then
        sed -e "s|__NPU_LISTEN_ADDR__|${npu_host}|g" \
            -e "s|__NPU_PORT__|${npu_port}|g" \
            "${NPU_DIR}/npu-exporter.service" > /etc/systemd/system/${NPU_SERVICE}.service
        systemctl daemon-reload
        log "  npu_exporter 配置已更新 (${npu_host}:${npu_port})"
    fi
}

# ── up ──────────────────────────────────────────────────────────────────────

do_up() {
    need_root
    log "========== up =========="

    log "[1/4] 更新 exporter 配置"
    update_exporter_configs

    log "[2/4] 启动 node_exporter"
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

    log "[3/4] 启动 npu_exporter"
    if systemctl cat "$NPU_SERVICE" &>/dev/null; then
        systemctl start "$NPU_SERVICE" 2>/dev/null || true
        systemctl start "$NPU_TIMER" 2>/dev/null || true
        systemctl is-active "$NPU_SERVICE" &>/dev/null \
            && log "  npu_exporter: running" \
            || log "  npu_exporter: timer will start on next boot"
    else
        log "  跳过：npu_exporter 未安装"
    fi

    log "[4/4] 启动 Docker 服务"
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
    docker compose down

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

    docker compose exec -T image-process \
        .venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8091/health')" \
        &>/dev/null \
        && _check "image-process    (internal)" 1 \
        || _check "image-process    (internal)" 0

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
INTERACTIVE=0
CLEAN=0

# 获取真实用户 home 目录（sudo 下 $HOME 可能是 /root）
if [ -n "$SUDO_USER" ]; then
    INSTALL_DIR="$(eval echo "~$SUDO_USER")/.agentos/.agent-manager"
else
    INSTALL_DIR="$HOME/.agentos/.agent-manager"
fi

# 扫描所有参数
for arg in "$@"; do
    case "$arg" in
        --interactive|-i) INTERACTIVE=1 ;;
        --clean)          CLEAN=1 ;;
    esac
done

# install 时先拷贝到 ~/.agentos/.agent-manager，然后指向新目录
if [ "$ACTION" = "install" ]; then
    mkdir -p "$INSTALL_DIR" || fail "无法创建目标目录: $INSTALL_DIR"
    log "拷贝 deploy 目录到 $INSTALL_DIR ..."
    cp -a "$DEPLOY_DIR"/. "$INSTALL_DIR"/

    DEPLOY_DIR="$INSTALL_DIR"
    NE_DIR="${DEPLOY_DIR}/node-exporter"
    NPU_DIR="${DEPLOY_DIR}/npu-exporter"

    log "后续操作将使用 ${DEPLOY_DIR} 中的内容执行"
fi

case "$ACTION" in
    install)   do_install ;;
    uninstall) do_uninstall ;;
    up)        do_up ;;
    down)      do_down ;;
    restart)   do_restart ;;
    status)    do_status ;;
    *)
        echo "用法: sudo bash $0 <command> [options]"
        echo ""
        echo "命令:"
        echo "  install   安装：拷贝到 ~/.agentos/.agent-manager 后执行（默认非交互）"
        echo "  uninstall 卸载：停止服务 + 注销 systemd（默认保留数据和 .env）"
        echo "  up        启动：更新 exporter 配置 → 启动服务"
        echo "  down      停止：docker compose → node/npu_exporter（反序）"
        echo "  restart   重启：down → up"
        echo "  status    查看服务状态"
        echo ""
        echo "选项:"
        echo "  --interactive, -i  交互式模式（install 时逐项询问，默认非交互）"
        echo "  --clean            uninstall 时删除数据卷和 .env"
        exit 1
        ;;
esac
