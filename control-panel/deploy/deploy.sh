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
#   sudo bash deploy.sh install              # 安装（默认非交互，单机 master）
#   sudo bash deploy.sh install -i           # 安装（交互式，可选 master/worker、多机监控）
#   sudo bash deploy.sh install --role worker
#   sudo bash deploy.sh install --role worker --master-ip 192.168.1.10
#   sudo bash deploy.sh install --mode multi --workers 192.168.1.11,192.168.1.12
#   sudo bash deploy.sh uninstall            # 卸载（默认保留数据和 .env）
#   sudo bash deploy.sh uninstall --clean    # 卸载（删除数据卷、.env 和安装目录）
#   sudo bash deploy.sh up                   # 启动：更新 exporter 配置 → 启动服务
#   sudo bash deploy.sh up --models '<JSON>' # 启动并手动指定模型配置（含 api_base，自包含）
#   sudo bash deploy.sh up --models-file /path/to/models.json
#   # models.json: {"api_base":"http://IP:8000/v1","api_key":"sk-xxx","models":[{"id":"qwen2.5-72b","max_model_len":32768}]}
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
ALLOY_DIR="${DEPLOY_DIR}/alloy"
ALLOY_CONTAINER="agentos-alloy"
ALLOY_IMAGE="grafana/alloy:v1.18.1"
ALLOY_DATA_HOST="/opt/agentos/alloy-data"
ALLOY_CONFIG_HOST="/opt/agentos/config.alloy"

# ── 工具函数 ────────────────────────────────────────────────────────────────

log()  { echo "[agentos] $*" >&2; }
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

# 带校验的 IP 输入（错误提示走 stderr，stdout 仅输出合法 IP）
read_ip() {
    local prompt="$1" default="$2" val
    while true; do
        read -erp "$prompt" val
        val="${val:-$default}"
        if valid_ipv4 "$val"; then
            echo "$val"
            return
        fi
        log "  ERROR: '$val' 不是有效的 IPv4 地址，请重新输入"
    done
}

# 录入 worker IP；成功时 stdout 仅输出 IP；输入 q/Q 结束录入（return 1）
read_worker_ip() {
    local prompt="$1" val
    while true; do
        read -erp "$prompt" val
        if [ "$val" = "q" ] || [ "$val" = "Q" ]; then
            return 1
        fi
        if [ -z "$val" ]; then
            log "  ERROR: 从节点 IP 不能为空（输入 'q' 结束添加）"
            continue
        fi
        if valid_ipv4 "$val"; then
            echo "$val"
            return 0
        fi
        log "  ERROR: '$val' 不是有效的 IPv4 地址，请重新输入（输入 'q' 结束添加）"
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

# URL 编码密码中的特殊字符（@ : / # ? & = % 等）
# 解决 docker-compose 里 POSTGRES_PASSWORD 嵌入 URL 时，@ 等字符破坏 URL 解析的问题
url_encode() {
    python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$1"
}

# 从 .env 直接读取 WORKER_NODES（bash source 会剥掉 JSON 内层双引号，如 ["ip"] → [ip]）
read_worker_nodes_json() {
    local env_file="${DEPLOY_DIR}/.env"
    ENV_FILE="$env_file" python3 <<'PY'
import os
from pathlib import Path

env_file = Path(os.environ.get("ENV_FILE", ""))
if not env_file.is_file():
    print("[]")
    raise SystemExit

for line in env_file.read_text(encoding="utf-8").splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    if not stripped.startswith("WORKER_NODES="):
        continue
    value = stripped.split("=", 1)[1].strip()
    if not value:
        print("[]")
        raise SystemExit
    if (value.startswith("'") and value.endswith("'")) or (
        value.startswith('"') and value.endswith('"')
    ):
        value = value[1:-1]
    print(value)
    raise SystemExit

print("[]")
PY
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

# 从 .env 读取 NODE_EXPORTER_HOST（不依赖 load_env）；空则自动检测本机 IP
resolve_master_exporter_host() {
    local env_file="${DEPLOY_DIR}/.env" host
    if [ ! -f "$env_file" ]; then
        detect_host_ip
        return
    fi

    host=$(grep -E '^NODE_EXPORTER_HOST=' "$env_file" | head -1 | cut -d= -f2-)
    host="${host//$'\r'/}"
    host="${host#"${host%%[![:space:]]*}"}"
    host="${host%"${host##*[![:space:]]}"}"
    host="${host#\'}"
    host="${host%\'}"
    host="${host#\"}"
    host="${host%\"}"

    if [ -z "$host" ] || [ "$host" = "0.0.0.0" ]; then
        detect_host_ip
    else
        printf '%s' "$host"
    fi
}

# 比较规范化前后 WORKER_NODES 是否变化（语义比较 JSON 数组）
worker_nodes_need_sync() {
    local raw="$1" sanitized="$2"
    RAW_JSON="$raw" SANITIZED_JSON="$sanitized" python3 <<'PY'
import json
import os
import sys

def load_list(raw: str) -> list:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []

raw = load_list(os.environ.get("RAW_JSON", "[]"))
sanitized = load_list(os.environ.get("SANITIZED_JSON", "[]"))
sys.exit(1 if raw != sanitized else 0)
PY
}

# 规范化 WORKER_NODES：去重并排除与 master 相同的 IP；stdout 输出 JSON 数组
sanitize_worker_nodes_json() {
    local master_host="$1" raw_json="$2"
    MASTER_HOST="$master_host" RAW_JSON="${raw_json:-[]}" python3 <<'PY'
import json
import os
import sys

master = os.environ.get("MASTER_HOST", "").strip()
raw = os.environ.get("RAW_JSON", "[]") or "[]"
try:
    nodes = json.loads(raw)
except json.JSONDecodeError:
    nodes = []
if not isinstance(nodes, list):
    nodes = []

seen = set()
result = []
for item in nodes:
    if not isinstance(item, str):
        continue
    host = item.strip()
    if not host or host in seen:
        if host in seen:
            print(f"[agentos]   跳过重复 worker IP: {host}", file=sys.stderr)
        continue
    if master and host == master:
        print(f"[agentos]   跳过与 master 相同的 worker IP: {host}", file=sys.stderr)
        continue
    seen.add(host)
    result.append(host)
print(json.dumps(result))
PY
}

# up 时若 .env 中 WORKER_NODES 含重复或与 master 相同 IP，写回规范化结果
sync_worker_nodes_env() {
    local env_file="${DEPLOY_DIR}/.env" ne_host raw sanitized
    [ -f "$env_file" ] || return

    ne_host=$(resolve_master_exporter_host)
    raw=$(read_worker_nodes_json)
    sanitized=$(sanitize_worker_nodes_json "$ne_host" "$raw")
    if worker_nodes_need_sync "$raw" "$sanitized"; then
        return
    fi

    _set_worker_nodes_json "$env_file" "$sanitized"
    log "  WORKER_NODES 已规范化: ${sanitized}"
}

# ── 节点角色 ────────────────────────────────────────────────────────────────

INSTALL_ROLE=""

node_role() {
    load_env
    env_default AGENTOS_NODE_ROLE master
}

is_master() {
    [ "$(node_role)" = "master" ]
}

is_worker() {
    [ "$(node_role)" = "worker" ]
}

_set_worker_nodes_json() {
    local env_file="$1" json="$2"
    # 外层单引号：避免 load_env/source .env 时剥掉 JSON 内的双引号
    sed -i "s|^WORKER_NODES=.*|WORKER_NODES='$(sed_escape "$json")'|" "$env_file"
}

_prompt_worker_nodes() {
    local env_file="$1"
    local workers=() host master_host w duplicate

    master_host=$(grep '^NODE_EXPORTER_HOST=' "$env_file" | head -1 | cut -d= -f2-)

    echo ""
    log "  多机监控：依次录入 worker IP（端口全集群统一），输入 'q' 结束添加"
    while true; do
        if ! host=$(read_worker_ip "  请添加从节点 IP (输入 'q' 结束添加): "); then
            break
        fi
        if [ -n "$master_host" ] && [ "$host" = "$master_host" ]; then
            log "  ERROR: 从节点 IP 不能与 master 本机 NODE_EXPORTER_HOST (${master_host}) 相同"
            continue
        fi
        duplicate=0
        for w in "${workers[@]}"; do
            if [ "$w" = "$host" ]; then
                duplicate=1
                break
            fi
        done
        if [ "$duplicate" -eq 1 ]; then
            log "  ERROR: 从节点 ${host} 已添加，请勿重复"
            continue
        fi

        workers+=("$host")
        log "  已添加从节点 ${host}"
    done

    local json="[]"
    if [ ${#workers[@]} -gt 0 ]; then
        local quoted=()
        for host in "${workers[@]}"; do
            quoted+=("\"${host}\"")
        done
        json="[$(IFS=,; echo "${quoted[*]}")]"
    fi
    _set_worker_nodes_json "$env_file" "$json"
    log "  WORKER_NODES = ${json}"
}

# 逗号分隔 worker IP → WORKER_NODES JSON（去重、校验、排除 master 本机）
_build_worker_nodes_json() {
    local csv="$1" master_host="$2"
    local workers=() host part duplicate
    local IFS=','

    read -ra parts <<< "$csv"
    for part in "${parts[@]}"; do
        host="${part//[[:space:]]/}"
        [ -z "$host" ] && continue
        valid_ipv4 "$host" || fail "无效的 worker IP: ${host}"
        if [ -n "$master_host" ] && [ "$host" = "$master_host" ]; then
            fail "worker IP 不能与 master 本机 NODE_EXPORTER_HOST (${master_host}) 相同: ${host}"
        fi
        duplicate=0
        for w in "${workers[@]}"; do
            if [ "$w" = "$host" ]; then
                duplicate=1
                log "  跳过重复 worker IP: ${host}"
                break
            fi
        done
        [ "$duplicate" -eq 1 ] && continue
        workers+=("$host")
    done
    [ ${#workers[@]} -gt 0 ] || fail "--workers 至少需要一个有效 IP"

    local quoted=()
    for host in "${workers[@]}"; do
        quoted+=("\"${host}\"")
    done
    echo "[$(IFS=,; echo "${quoted[*]}")]"
}

# 非交互 master：仅 CLI --workers / --mode，默认单机 []
_resolve_worker_nodes_for_master() {
    local ne_host="$1"

    if [ -n "$INSTALL_WORKERS" ]; then
        _build_worker_nodes_json "$INSTALL_WORKERS" "$ne_host"
    else
        echo "[]"
    fi
}

_init_env_worker_noninteractive() {
    local env_file="$1"
    local detected_ip ne_host npu_host master_ip

    detected_ip=$(detect_host_ip)
    ne_host="${NODE_EXPORTER_HOST:-$detected_ip}"
    npu_host="${NPU_EXPORTER_HOST:-$detected_ip}"
    master_ip="${MASTER_IP:-}"

    sed -i "s/^NODE_EXPORTER_HOST=.*/NODE_EXPORTER_HOST=$(sed_escape "$ne_host")/" "$env_file"
    sed -i "s/^NPU_EXPORTER_HOST=.*/NPU_EXPORTER_HOST=$(sed_escape "$npu_host")/" "$env_file"
    if [ -n "$master_ip" ]; then
        sed -i "s/^MASTER_IP=.*/MASTER_IP=$(sed_escape "$master_ip")/" "$env_file"
    fi
    _set_worker_nodes_json "$env_file" "[]"

    log "  worker 非交互模式："
    log "  NODE_EXPORTER_HOST = ${ne_host}"
    log "  NPU_EXPORTER_HOST  = ${npu_host}"
    [ -n "$master_ip" ] && log "  MASTER_IP          = ${master_ip}"
}

_init_env_worker_interactive() {
    local env_file="$1" val detected_ip

    detected_ip=$(detect_host_ip)
    echo ""
    log "  worker 节点：需配置本机 exporter 地址及 master IP"
    echo ""

    val=$(read_ip "NODE_EXPORTER_HOST [${detected_ip}]: " "$detected_ip")
    sed -i "s/^NODE_EXPORTER_HOST=.*/NODE_EXPORTER_HOST=$(sed_escape "$val")/" "$env_file"
    log "  NODE_EXPORTER_HOST = ${val}"

    val=$(read_ip "NPU_EXPORTER_HOST [${detected_ip}]: " "$detected_ip")
    sed -i "s/^NPU_EXPORTER_HOST=.*/NPU_EXPORTER_HOST=$(sed_escape "$val")/" "$env_file"
    log "  NPU_EXPORTER_HOST = ${val}"

    echo ""
    val=$(read_ip "MASTER_IP (master 节点 IP，用于 Alloy 日志上报) []: " "")
    if [ -n "$val" ]; then
        sed -i "s/^MASTER_IP=.*/MASTER_IP=$(sed_escape "$val")/" "$env_file"
        log "  MASTER_IP = ${val}"
    else
        log "  MASTER_IP = (未设置，Alloy 日志上报需手动配置)"
    fi

    _set_worker_nodes_json "$env_file" "[]"
}

need_root() {
    [ "$(id -u)" -eq 0 ] || fail "需要 root 权限。请用: sudo bash $0 $ACTION"
}

# 获取真实用户 home 目录（sudo 下 $HOME 可能是 /root）
if [ -n "$SUDO_USER" ]; then
    INSTALL_DIR="$(eval echo "~$SUDO_USER")/.agentos/.agent-manager"
else
    INSTALL_DIR="$HOME/.agentos/.agent-manager"
fi

# 检查是否在安装目录下操作（up/down/restart/status/uninstall 需要）
need_install_dir() {
    if [ "$DEPLOY_DIR" != "$INSTALL_DIR" ]; then
        fail "请先切换到安装目录后再执行此操作:
  cd ${INSTALL_DIR}
  sudo bash deploy.sh $ACTION"
    fi
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
        local role_val
        read -rp "节点角色 (master/worker) [master]: " role_val
        INSTALL_ROLE="${role_val:-master}"
    else
        INSTALL_ROLE="${INSTALL_ROLE_CLI:-master}"
        case "$INSTALL_ROLE" in
            master|worker) ;;
            *) fail "--role 必须是 master 或 worker" ;;
        esac
    fi
    sed -i "s/^AGENTOS_NODE_ROLE=.*/AGENTOS_NODE_ROLE=$(sed_escape "$INSTALL_ROLE")/" "$env_file"

    if [ "$INSTALL_ROLE" = "worker" ]; then
        if [ "$INTERACTIVE" -eq 1 ]; then
            _init_env_worker_interactive "$env_file"
        else
            [ -n "$INSTALL_MASTER_IP" ] && export MASTER_IP="$INSTALL_MASTER_IP"
            _init_env_worker_noninteractive "$env_file"
        fi
    elif [ "$INTERACTIVE" -eq 1 ]; then
        _init_env_interactive "$env_file"
    else
        _init_env_noninteractive "$env_file"
    fi

    # 初始化成功，取消 trap
    trap - EXIT

    echo ""
    log ".env 已生成。"
}

# 非交互式：优先读取环境变量，未设置则自动生成/使用默认值
_init_env_noninteractive() {
    local env_file="$1"

    # 用户名/密码：优先读环境变量，未设置则用默认值/自动生成
    local pg_user="${POSTGRES_USER:-agentos}"
    local pg_user="${POSTGRES_USER:-agentos}"
    local pg_pass="${POSTGRES_PASSWORD:-agentos123}"
    local pg_pass_encoded
    pg_pass_encoded=$(url_encode "$pg_pass")
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
    local register_url="${AGENT_REGISTER_URL:-http://${detected_ip}:4003}"

    sed -i "s/^POSTGRES_USER=.*/POSTGRES_USER=$(sed_escape "$pg_user")/" "$env_file"
    sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(sed_escape "$pg_pass_encoded")/" "$env_file"
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

    # 检测 agentos 系统用户 UID/GID（默认 1000）
    local sys_uid sys_gid
    sys_uid="${AGENTOS_SYS_UID:-$(id -u agentos 2>/dev/null || echo 1000)}"
    sys_gid="${AGENTOS_SYS_GID:-$(id -g agentos 2>/dev/null || echo 1000)}"
    sed -i "s/^AGENTOS_SYS_UID=.*/AGENTOS_SYS_UID=${sys_uid}/" "$env_file"
    sed -i "s/^AGENTOS_SYS_GID=.*/AGENTOS_SYS_GID=${sys_gid}/" "$env_file"

    local worker_json
    worker_json=$(_resolve_worker_nodes_for_master "$ne_host")
    _set_worker_nodes_json "$env_file" "$worker_json"

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
    log "  WORKER_NODES       = ${worker_json}"
    log "  AGENTOS_SYS_UID    = ${sys_uid}"
    log "  AGENTOS_SYS_GID    = ${sys_gid}"
}

# 交互式：逐项询问用户
_init_env_interactive() {
    local env_file="$1" val

    read -rp "POSTGRES_USER [agentos]: " val
    sed -i "s/^POSTGRES_USER=.*/POSTGRES_USER=$(sed_escape "${val:-agentos}")/" "$env_file"

    read -rsp "POSTGRES_PASSWORD: " val; echo
    [ -n "$val" ] || fail "POSTGRES_PASSWORD 不能为空"
    local pg_enc_val
    pg_enc_val=$(url_encode "$val")
    sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(sed_escape "$pg_enc_val")/" "$env_file"

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

    echo ""
    read -rp "启用多机监控? (y/N): " val
    if [ "$val" = "y" ] || [ "$val" = "Y" ]; then
        _prompt_worker_nodes "$env_file"
    else
        _set_worker_nodes_json "$env_file" "[]"
        log "  WORKER_NODES = []"
    fi

    # 自动检测 agentos 系统用户 UID/GID
    local sys_uid sys_gid
    sys_uid=$(id -u agentos 2>/dev/null || echo 1000)
    sys_gid=$(id -g agentos 2>/dev/null || echo 1000)
    sed -i "s/^AGENTOS_SYS_UID=.*/AGENTOS_SYS_UID=${sys_uid}/" "$env_file"
    sed -i "s/^AGENTOS_SYS_GID=.*/AGENTOS_SYS_GID=${sys_gid}/" "$env_file"
    log "  AGENTOS_SYS_UID = ${sys_uid} (从 agentos 用户检测)"
    log "  AGENTOS_SYS_GID = ${sys_gid} (从 agentos 用户检测)"
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
print('agent-base:1.0')
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
            "grafana/loki:3.6.0"
            "grafana/alloy:v1.18.1"
            "agent-base:1.0"
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
    local failed=0
    for img in "${missing[@]}"; do
        if [[ "$img" == agentos-control-panel:* ]]; then
            docker compose pull agentos 2>/dev/null || {
                log "  WARNING: $img 拉取失败，请先本地构建:"
                log "    cd control-panel && docker build -f image/Dockerfile -t agentos ."
                failed=1
            }
        elif [[ "$img" == agent-base:* ]]; then
            docker pull "$img" 2>/dev/null || {
                log "  WARNING: $img 拉取失败，请先推送至仓库或 docker load 导入本机"
                failed=1
            }
        elif [[ "$img" == agentos-image-process:* ]]; then
            docker compose pull image-process 2>/dev/null || {
                log "  WARNING: $img 拉取失败，请先推送至仓库或 docker load 导入本机"
                failed=1
            }
        else
            log "  拉取 $img ..."
            docker pull "$img" 2>/dev/null || { log "  WARNING: $img 拉取失败"; failed=1; }
        fi
    done

    if [ "$failed" -eq 1 ]; then
        log "WARNING: 部分镜像拉取失败，请检查上方日志。"
    else
        log "镜像就绪。"
    fi
}

# ── node_exporter 安装/卸载 ────────────────────────────────────────────────

install_node_exporter() {
    local ne_port ne_host listen_addr
    ne_port=$(env_default NODE_EXPORTER_PORT 8091)
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
    npu_port=$(env_default NPU_EXPORTER_PORT 8092)
    npu_host=$(env_default NPU_EXPORTER_HOST 127.0.0.1)

    # 创建运行用户
    if ! getent group "$NPU_RUN_GROUP" &>/dev/null; then
        if ! groupadd -r "$NPU_RUN_GROUP" 2>/dev/null; then
            if ! groupadd "$NPU_RUN_GROUP" 2>/dev/null; then
                fail "创建用户组 '$NPU_RUN_GROUP' 失败，请检查系统权限或是否存在同名冲突"
            fi
        fi
        log "  已创建用户组 '$NPU_RUN_GROUP'"
    fi
    if ! id "$NPU_RUN_USER" &>/dev/null; then
        if ! useradd -r -g "$NPU_RUN_GROUP" -s /sbin/nologin "$NPU_RUN_USER" 2>/dev/null; then
            if ! useradd -g "$NPU_RUN_GROUP" -s /sbin/nologin "$NPU_RUN_USER" 2>/dev/null; then
                fail "创建用户 '$NPU_RUN_USER' 失败，请检查系统权限或是否存在同名冲突"
            fi
        fi
        log "  已创建用户 '$NPU_RUN_USER'"
    fi

    # 创建日志目录结构
    mkdir -p /home/agentos/logs
    chmod 755 /home/agentos/logs
    mkdir -p /home/agentos/logs/npu_exporter
    chown "$NPU_RUN_USER:$NPU_RUN_GROUP" /home/agentos/logs/npu_exporter
    log "  已创建日志目录 /home/agentos/logs/npu_exporter"

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

    # 创建日志文件
    touch /home/agentos/logs/npu_exporter/npu-exporter.log
    chown "$NPU_RUN_USER:$NPU_RUN_GROUP" /home/agentos/logs/npu_exporter/npu-exporter.log
    log "  已创建日志文件 /home/agentos/logs/npu_exporter/npu-exporter.log"
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

# ── alloy 安装/卸载（仅 worker 节点；master 由 docker compose 管理）──────────────

install_alloy() {
    is_worker || { log "  master 节点：Alloy 由 docker compose 管理，跳过独立安装"; return; }

    local cfg="${ALLOY_DIR}/config.alloy"
    [ -f "$cfg" ] || { log "  WARNING: ${cfg} 不存在，跳过 Alloy 安装"; return 1; }
    command -v docker &>/dev/null || fail "Alloy 安装需要 Docker"

    local loki_endpoint master_ip
    master_ip=$(env_default MASTER_IP "")
    if [ -n "$master_ip" ]; then
        loki_endpoint=$(env_default ALLOY_LOKI_ENDPOINT "http://${master_ip}:8096/loki/api/v1/push")
    else
        loki_endpoint=$(env_default ALLOY_LOKI_ENDPOINT "http://loki:8096/loki/api/v1/push")
    fi

    # 如果已有容器在运行，先停止
    if docker ps -a --format '{{.Names}}' | grep -q "^${ALLOY_CONTAINER}$"; then
        docker stop "$ALLOY_CONTAINER" 2>/dev/null || true
        docker rm "$ALLOY_CONTAINER" 2>/dev/null || true
    fi

    mkdir -p "$ALLOY_DATA_HOST"

    # 生成 worker 端 config.alloy（替换 Loki endpoint）
    sed "s|http://loki:8096/loki/api/v1/push|$(sed_escape "$loki_endpoint")|g" \
        "$cfg" > "$ALLOY_CONFIG_HOST"
    log "  Alloy 配置已生成: ${ALLOY_CONFIG_HOST} (loki: ${loki_endpoint})"

    # 检测/拉取镜像
    if docker image inspect "$ALLOY_IMAGE" &>/dev/null; then
        log "  Alloy 镜像已存在: ${ALLOY_IMAGE}"
    else
        log "  拉取 Alloy 镜像 ${ALLOY_IMAGE} ..."
        docker pull "$ALLOY_IMAGE" || fail "Alloy 镜像拉取失败: ${ALLOY_IMAGE}"
    fi

    # 创建容器（不启动，由 do_up 统一管理）
    docker create \
        --name "$ALLOY_CONTAINER" \
        --restart unless-stopped \
        --network host \
        -v "${ALLOY_CONFIG_HOST}:/etc/alloy/config.alloy:ro" \
        -v "${ALLOY_DATA_HOST}:/etc/alloy/data" \
        -v /root:/home/agentos/host_root:ro \
        -v /home/agentos:/home/agentos:ro \
        -v /tmp/yr_sessions:/tmp/yr_sessions:ro \
        -v /tmp/jiuwenbox:/tmp/jiuwenbox:ro \
        "$ALLOY_IMAGE" \
        run --server.http.listen-addr=127.0.0.1:12345 --storage.path=/etc/alloy/data /etc/alloy/config.alloy \
        2>/dev/null || fail "Alloy 容器创建失败"

    log "  Alloy 容器已创建"
}

uninstall_alloy() {
    if ! docker ps -a --format '{{.Names}}' | grep -q "^${ALLOY_CONTAINER}$"; then
        log "  跳过：Alloy 容器不存在"
        return
    fi

    docker stop "$ALLOY_CONTAINER" 2>/dev/null || true
    docker rm "$ALLOY_CONTAINER" 2>/dev/null || true
    log "  已移除 Alloy 容器"

    if [ "$CLEAN" -eq 1 ]; then
        [ -f "$ALLOY_CONFIG_HOST" ] && rm -f "$ALLOY_CONFIG_HOST" && log "  已删除 ${ALLOY_CONFIG_HOST}"
        [ -d "$ALLOY_DATA_HOST" ] && rm -rf "$ALLOY_DATA_HOST" && log "  已删除 ${ALLOY_DATA_HOST}"
    else
        log "  保留 ${ALLOY_CONFIG_HOST} 和 ${ALLOY_DATA_HOST}（使用 --clean 彻底删除）"
    fi
}

# ── install ─────────────────────────────────────────────────────────────────

do_install() {
    need_root
    log "========== install =========="

    log "[1/5] 初始化 .env"
    init_env
    load_env

    log "[2/5] 安装 node_exporter"
    install_node_exporter || true

    log "[3/5] 安装 npu_exporter"
    install_npu_exporter || true

    log "[4/5] 安装 Alloy"
    install_alloy || true

    if is_master; then
        log "[5/5] 拉取 Docker 镜像"
        pull_images
    else
        log "[5/5] worker 节点跳过 Docker 镜像拉取"
    fi

    log "install 完成。"
    echo ""
    log "提示: 如需修改端口等配置，可直接编辑 ${DEPLOY_DIR}/.env"
    log "后续操作请先切换到安装目录:"
    log "  cd ${DEPLOY_DIR}"
    log "  sudo bash deploy.sh up"
}

# ── uninstall ───────────────────────────────────────────────────────────────

do_uninstall() {
    need_root
    need_install_dir
    log "========== uninstall =========="

    if is_master; then
        log "[1/4] 停止 Docker 服务"
        cd "$DEPLOY_DIR"
        if [ "$CLEAN" -eq 1 ]; then
            docker compose down -v || true
            log "  已停止并删除数据卷"
        else
            docker compose down || true
            log "  已停止（数据卷保留）"
        fi
    else
        log "[1/4] worker 节点跳过 Docker 服务"
    fi

    log "[2/4] 注销 Alloy"
    uninstall_alloy

    log "[3/4] 注销 node_exporter"
    uninstall_node_exporter

    log "[4/4] 注销 npu_exporter"
    uninstall_npu_exporter

    if [ "$CLEAN" -eq 1 ] && [ -d "$INSTALL_DIR" ]; then
        cd /
        rm -rf "$INSTALL_DIR"
        log "  已删除安装目录 $INSTALL_DIR"
    fi

    log "uninstall 完成。"
}

# ── 更新 exporter 服务配置 ──────────────────────────────────────────────

update_exporter_configs() {
    load_env

    local ne_port ne_host ne_listen
    ne_port=$(env_default NODE_EXPORTER_PORT 8091)
    ne_host=$(env_default NODE_EXPORTER_HOST 127.0.0.1)
    if [ -z "$ne_host" ] || [ "$ne_host" = "0.0.0.0" ]; then
        ne_listen=":${ne_port}"
    else
        ne_listen="${ne_host}:${ne_port}"
    fi

    if [ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]; then
        if systemctl is-active "$SERVICE_NAME" &>/dev/null; then
            systemctl stop "$SERVICE_NAME"
            log "  node_exporter 已停止"
        fi
        sed "s|__LISTEN_ADDR__|${ne_listen}|" \
            "${NE_DIR}/node_exporter.service" > /etc/systemd/system/${SERVICE_NAME}.service
        systemctl daemon-reload
        log "  node_exporter 配置已更新 (${ne_listen})"
    fi

    local npu_port npu_host
    npu_port=$(env_default NPU_EXPORTER_PORT 8092)
    npu_host=$(env_default NPU_EXPORTER_HOST 127.0.0.1)

    if [ -f "/etc/systemd/system/${NPU_SERVICE}.service" ]; then
        if systemctl is-active "$NPU_SERVICE" &>/dev/null; then
            systemctl stop "$NPU_TIMER" 2>/dev/null || true
            systemctl stop "$NPU_SERVICE" 2>/dev/null || true
            log "  npu_exporter 已停止"
        fi
        sed -e "s|__NPU_LISTEN_ADDR__|${npu_host}|g" \
            -e "s|__NPU_PORT__|${npu_port}|g" \
            "${NPU_DIR}/npu-exporter.service" > /etc/systemd/system/${NPU_SERVICE}.service
        systemctl daemon-reload
        log "  npu_exporter 配置已更新 (${npu_host}:${npu_port})"
    fi
}

# ── up ──────────────────────────────────────────────────────────────────────

generate_hardware_metrics_json() {
    local json_file="${DEPLOY_DIR}/victoriametrics/hardware-metrics.json"
    local ne_host ne_port npu_port worker_json

    ne_host=$(resolve_master_exporter_host)
    load_env
    ne_port=$(env_default NODE_EXPORTER_PORT 8091)
    npu_port=$(env_default NPU_EXPORTER_PORT 8092)
    worker_json=$(read_worker_nodes_json)
    worker_json=$(sanitize_worker_nodes_json "$ne_host" "$worker_json")

    NE_HOST="$ne_host" NE_PORT="$ne_port" NPU_PORT="$npu_port" WORKER_NODES_JSON="$worker_json" \
        python3 <<'PY' > "$json_file"
import json
import os

ne_host = os.environ["NE_HOST"]
ne_port = os.environ["NE_PORT"]
npu_port = os.environ["NPU_PORT"]
unique_hosts = json.loads(os.environ.get("WORKER_NODES_JSON", "[]") or "[]")
if not isinstance(unique_hosts, list):
    unique_hosts = []

targets = [
    {
        "targets": [f"{ne_host}:{ne_port}"],
        "labels": {"exporter": "node", "node": "master", "host": ne_host},
    },
    {
        "targets": [f"{ne_host}:{npu_port}"],
        "labels": {"exporter": "npu", "node": "master", "host": ne_host},
    },
]

for index, host in enumerate(unique_hosts, start=1):
    worker_id = f"worker-{index}"

    targets.append(
        {
            "targets": [f"{host}:{ne_port}"],
            "labels": {"exporter": "node", "node": worker_id, "host": host},
        }
    )
    targets.append(
        {
            "targets": [f"{host}:{npu_port}"],
            "labels": {"exporter": "npu", "node": worker_id, "host": host},
        }
    )

print(json.dumps(targets, indent=2))
PY

    log "  hardware-metrics.json 已生成 (${json_file})"
}

_sniff_initial_models() {
    # 配置推理服务模型信息，写入 .env
    # 参数：$1=命令行 JSON（--models），$2=JSON 文件路径（--models-file）
    #
    # 手动模式（传了 --models / --models-file）：
    #   JSON 格式：{"api_base":"...","api_key":"...","models":[{...},...]}
    #   - api_base 必填，api_key 可选
    #   - 用 api_base 嗅探校验：用户填了和嗅探不一致报错，没填的用嗅探补全
    #   - 写入 .env：INITIAL_MODEL_API_BASE + INITIAL_MODEL_API_KEY + INITIAL_MODELS
    # 纯嗅探模式（没传参数，.env 也没有 INITIAL_MODELS）：
    #   - 用 .env 的 INITIAL_MODEL_API_BASE 嗅探，直接用嗅探结果
    local models_json_arg="${1:-}"
    local models_file_arg="${2:-}"
    local env_file="${DEPLOY_DIR}/.env"

    load_env

    local models_input=""

    # ── 判断来源 ──
    if [ -n "$models_json_arg" ]; then
        models_input="$models_json_arg"
        log "  从命令行 --models 读取模型配置"
    elif [ -n "$models_file_arg" ]; then
        [ -f "$models_file_arg" ] || fail "模型配置文件不存在: $models_file_arg"
        models_input=$(cat "$models_file_arg")
        log "  从文件 --models-file 读取模型配置: $models_file_arg"
    elif [ -n "${INITIAL_MODELS:-}" ]; then
        log "  .env 已有 INITIAL_MODELS，跳过"
        return 0
    fi

    MODELS_INPUT="$models_input" \
    ENV_API_BASE="${INITIAL_MODEL_API_BASE:-}" \
    ENV_API_KEY="${INITIAL_MODEL_API_KEY:-}" \
    ENV_FILE="$env_file" \
    python3 <<'PYEOF'
import json, os, re, urllib.request, urllib.error
from urllib.parse import urlparse

models_input = os.environ.get("MODELS_INPUT", "")
env_api_base = os.environ.get("ENV_API_BASE", "")
env_api_key = os.environ.get("ENV_API_KEY", "")
env_file = os.environ["ENV_FILE"]

manual_mode = bool(models_input)

# ── 解析手动输入 ──
manual_items = []
api_base = ""
api_key = ""

if manual_mode:
    try:
        parsed = json.loads(models_input)
    except json.JSONDecodeError as e:
        print(f"[agentos] ERROR: JSON 解析失败: {e}")
        exit(1)

    if not isinstance(parsed, dict):
        print("[agentos] ERROR: 手动配置必须是对象 {\"api_base\":...,\"models\":[...]}")
        exit(1)

    api_base = parsed.get("api_base", "")
    api_key = parsed.get("api_key", "")
    if not api_base:
        print('[agentos] ERROR: 手动配置缺少 api_base 字段')
        exit(1)

    manual_items = parsed.get("models", [])
    if not isinstance(manual_items, list):
        print("[agentos] ERROR: models 字段必须是数组")
        exit(1)
    # models 为空 → 嗅探所有模型；有内容 → 只校验+补全列出的模型
else:
    # 纯嗅探模式：用 .env 的 INITIAL_MODEL_API_BASE
    api_base = env_api_base
    api_key = env_api_key
    if not api_base:
        print("[agentos] 无手动配置且无 INITIAL_MODEL_API_BASE，跳过")
        exit(0)

api_base = api_base.rstrip("/")
log_prefix = "手动配置校验" if manual_mode else "嗅探"
print(f"[agentos] {log_prefix}推理服务: {api_base}/models")

# ── 嗅探推理服务 ──
sniffed_models = []
try:
    url = f"{api_base}/models"
    req = urllib.request.Request(url)
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    sniffed_models = data.get("data", [])
    if not sniffed_models:
        print(f"[agentos] WARNING: 推理服务 {url} 返回为空")
except urllib.error.URLError as e:
    print(f"[agentos] WARNING: 无法连接推理服务 {api_base}/models: {e}")
    exit(0)
except Exception as e:
    print(f"[agentos] WARNING: 嗅探失败: {e}")
    exit(0)

# 嗅探结果按 id 索引
sniffed_map = {}
for m in sniffed_models:
    mid = m.get("id", "")
    if mid:
        sniffed_map[mid] = m

def merge_field(user_val, sniffed_val, field, model_id):
    """合并字段：用户填了优先，和嗅探到的不一致报错，没填用嗅探的"""
    if user_val is not None:
        if sniffed_val is not None and user_val != sniffed_val:
            print(f"[agentos] ERROR: 模型 '{model_id}' 的 {field} 不一致：用户填 '{user_val}'，嗅探到 '{sniffed_val}'")
            exit(1)
        return user_val
    return sniffed_val

# ── 构建结果 ──
result = []
owned_by = None

if manual_mode and manual_items:
    # 手动模式 + models 有内容：校验 + 补全列出的模型
    for m in manual_items:
        model_id = m.get("id", "")
        if not model_id:
            print(f"[agentos] ERROR: 条目缺少 id 字段: {m}")
            exit(1)

        sniffed = sniffed_map.get(model_id)
        if sniffed is None:
            print(f"[agentos] ERROR: 模型 '{model_id}' 在推理服务 {api_base} 中不存在")
            exit(1)

        # 校验 + 补全
        item = {"id": model_id}
        merged_mml = merge_field(
            m.get("max_model_len"), sniffed.get("max_model_len"), "max_model_len", model_id
        )
        if merged_mml is not None:
            item["max_model_len"] = merged_mml
        merged_ob = merge_field(
            m.get("owned_by"), sniffed.get("owned_by"), "owned_by", model_id
        )
        if merged_ob:
            item["owned_by"] = merged_ob
            if owned_by is None:
                owned_by = merged_ob

        result.append(item)

    print(f"[agentos] 手动配置校验通过，{len(result)} 个模型")

else:
    # 纯嗅探模式 或 手动模式 models 为空：直接用嗅探结果
    for m in sniffed_models:
        model_id = m.get("id", "")
        if not model_id:
            continue
        item = {"id": model_id}
        if m.get("max_model_len") is not None:
            item["max_model_len"] = m["max_model_len"]
        if m.get("owned_by"):
            item["owned_by"] = m["owned_by"]
            if owned_by is None:
                owned_by = m["owned_by"]
        result.append(item)
    print(f"[agentos] 嗅探到 {len(result)} 个模型: {[m['id'] for m in result]}")

if not result:
    print("[agentos] WARNING: 未获取到任何模型信息")
    exit(0)

# ── 推导 inference_engine 和 metrics_url ──
models_json = json.dumps(result, ensure_ascii=False)

parsed = urlparse(api_base)
api_ip = parsed.hostname or "127.0.0.1"

inference_engine = ""
metrics_url = ""
if owned_by == "motor":
    inference_engine = "vllm"
    metrics_url = f"http://{api_ip}:1029"
elif owned_by == "local":
    inference_engine = "sglang"
    metrics_url = f"http://{api_ip}:1025"
elif owned_by == "sglang":
    inference_engine = "sglang"
    metrics_url = f"http://{api_ip}:8003"

# ── 写入 .env ──
with open(env_file, "r", encoding="utf-8") as f:
    content = f.read()

def update_env(content, key, value):
    pattern = r"^" + key + r"=.*$"
    replacement = f"{key}={value}"
    if re.search(pattern, content, re.MULTILINE):
        return re.sub(pattern, replacement, content, count=1, flags=re.MULTILINE)
    else:
        return content + f"\n{replacement}\n"

# 手动模式：写入 api_base 和 api_key（供后端注册到 LiteLLM 用）
if manual_mode:
    content = update_env(content, "INITIAL_MODEL_API_BASE", api_base)
    if api_key:
        content = update_env(content, "INITIAL_MODEL_API_KEY", api_key)

# 写入 INITIAL_MODELS
content = update_env(content, "INITIAL_MODELS", f"'{models_json}'")

# 写入 INITIAL_INFERENCE_ENGINE
if inference_engine:
    content = update_env(content, "INITIAL_INFERENCE_ENGINE", inference_engine)

# 写入 INITIAL_MODEL_METRICS_URL
if metrics_url:
    content = update_env(content, "INITIAL_MODEL_METRICS_URL", metrics_url)

with open(env_file, "w", encoding="utf-8") as f:
    f.write(content)

print(f"[agentos] 已写入 INITIAL_MODELS 到 {env_file}")
if inference_engine:
    print(f"[agentos] owned_by={owned_by}, INITIAL_INFERENCE_ENGINE={inference_engine}, INITIAL_MODEL_METRICS_URL={metrics_url}")
PYEOF
}

do_up() {
    need_root
    need_install_dir
    log "========== up =========="

    # --models / --models-file 由全局参数解析存入 UP_MODELS_JSON / UP_MODELS_FILE

    log "[1/7] 更新 exporter 配置"
    update_exporter_configs

    log "[2/7] 启动 node_exporter"
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

    log "[3/7] 启动 npu_exporter"
    if systemctl cat "$NPU_SERVICE" &>/dev/null; then
        systemctl start "$NPU_SERVICE" 2>/dev/null || true
        systemctl start "$NPU_TIMER" 2>/dev/null || true
        systemctl is-active "$NPU_SERVICE" &>/dev/null \
            && log "  npu_exporter: running" \
            || log "  npu_exporter: timer will start on next boot"
    else
        log "  跳过：npu_exporter 未安装"
    fi

    log "[4/7] 启动 Alloy"
    if is_worker; then
        if docker ps -a --format '{{.Names}}' | grep -q "^${ALLOY_CONTAINER}$"; then
            docker start "$ALLOY_CONTAINER" 2>/dev/null || true
            log "  Alloy: started"
        else
            log "  WARNING: Alloy 容器不存在，请先执行: sudo bash $0 install"
        fi
    else
        log "  master 节点：Alloy 由 docker compose 管理"
    fi

    log "[5/7] 生成 hardware-metrics.json"
    if is_master; then
        sync_worker_nodes_env
        generate_hardware_metrics_json
    else
        log "  跳过：worker 节点无需生成"
    fi

    log "[6/7] 配置推理服务模型"
    if is_master; then
        _sniff_initial_models "$UP_MODELS_JSON" "$UP_MODELS_FILE"
    else
        log "  跳过：worker 节点无需配置"
    fi

    log "[7/7] 启动 Docker 服务"
    if is_master; then
        cd "$DEPLOY_DIR"
        docker compose up -d

        log "等待服务就绪 ..."
        sleep 3

        do_status
    else
        log "  worker 节点跳过 Docker 服务"
        do_status
    fi
}

# ── down ────────────────────────────────────────────────────────────────────

do_down() {
    need_root
    need_install_dir
    log "========== down =========="

    log "[1/4] 停止 Docker 服务"
    if is_master; then
        cd "$DEPLOY_DIR"
        docker compose down
    else
        log "  worker 节点跳过 Docker 服务"
    fi

    log "[2/4] 停止 Alloy"
    if is_worker; then
        docker stop "$ALLOY_CONTAINER" 2>/dev/null || true
        log "  Alloy: stopped"
    else
        log "  master 节点：Alloy 由 docker compose 管理"
    fi

    log "[3/4] 停止 node_exporter"
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    log "  node_exporter: stopped"

    log "[4/4] 停止 npu_exporter"
    systemctl stop "$NPU_TIMER" 2>/dev/null || true
    systemctl stop "$NPU_SERVICE" 2>/dev/null || true
    log "  npu_exporter: stopped"

    log "down 完成。"
}

# ── restart ───────────────────────────────────────────────────────────

do_restart() {
    need_install_dir
    do_down
    do_up
}

# ── status ──────────────────────────────────────────────────────────────────
do_status() {
    need_install_dir
    load_env
    local ne_port ne_host npu_port npu_host frontend_port litellm_port litellm_host postgres_port victoriametrics_port grafana_port
    ne_port=$(env_default NODE_EXPORTER_PORT 8091)
    ne_host=$(env_default NODE_EXPORTER_HOST 127.0.0.1)
    npu_port=$(env_default NPU_EXPORTER_PORT 8092)
    npu_host=$(env_default NPU_EXPORTER_HOST 127.0.0.1)
    frontend_port=$(env_default FRONTEND_PORT 8090)
    litellm_port=$(env_default LITELLM_PORT 8100)
    litellm_host=$(env_default LITELLM_HOST 127.0.0.1)
    postgres_port=$(env_default POSTGRES_PORT 5432)
    victoriametrics_port=$(env_default VICTORIAMETRICS_PORT 8428)
    grafana_port=$(env_default GRAFANA_PORT 8093)

    echo ""
    if is_master; then
        log "--- docker compose ps ---"
        cd "$DEPLOY_DIR"
        docker compose ps 2>/dev/null
    else
        log "--- worker 节点（无 Docker Compose）---"
    fi

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

    curl --connect-timeout 3 --max-time 5 -sf "http://${ne_host}:${ne_port}/metrics" &>/dev/null \
        && _check "node_exporter    (${ne_host}:${ne_port})" 1 \
        || _check "node_exporter    (${ne_host}:${ne_port})" 0

    curl --connect-timeout 3 --max-time 5 -sf "http://${npu_host}:${npu_port}/metrics" &>/dev/null \
        && _check "npu_exporter     (${npu_host}:${npu_port})" 1 \
        || _check "npu_exporter     (${npu_host}:${npu_port})" 0

    curl --connect-timeout 3 --max-time 5 -sfI "http://127.0.0.1:${frontend_port}/" &>/dev/null \
        && _check "frontend         (:${frontend_port})" 1 \
        || _check "frontend         (:${frontend_port})" 0

        docker compose exec -T image-process \
            .venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8091/health')" \
            &>/dev/null \
            && _check "image-process    (internal)" 1 \
            || _check "image-process    (internal)" 0

    docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-agentos}" 2>/dev/null | grep -qi accepting \
        && _check "postgres         (127.0.0.1:${postgres_port})" 1 \
        || _check "postgres         (127.0.0.1:${postgres_port})" 0

    curl --connect-timeout 3 --max-time 5 -sf "http://${litellm_host}:${litellm_port}/health/liveliness" 2>/dev/null | grep -qi alive \
        && _check "litellm          (${litellm_host}:${litellm_port})" 1 \
        || _check "litellm          (${litellm_host}:${litellm_port})" 0

    curl --connect-timeout 3 --max-time 5 -sf "http://127.0.0.1:${victoriametrics_port}/health" 2>/dev/null | grep -qi ok \
        && _check "victoriametrics  (:${victoriametrics_port})" 1 \
        || _check "victoriametrics  (:${victoriametrics_port})" 0

    curl --connect-timeout 3 --max-time 5 -sf "http://127.0.0.1:${grafana_port}/api/health" 2>/dev/null | grep -qi ok \
        && _check "grafana          (:${grafana_port})" 1 \
        || _check "grafana          (:${grafana_port})" 0

    curl --connect-timeout 3 --max-time 5 -sf "http://127.0.0.1:12345/ready" &>/dev/null \
        && _check "alloy            (127.0.0.1:12345)" 1 \
        || _check "alloy            (127.0.0.1:12345)" 0

    unset -f _check
    echo ""
}

# ── 入口 ────────────────────────────────────────────────────────────────────

validate_install_cli() {
    if [ "$INTERACTIVE" -eq 1 ]; then
        if [ -n "$INSTALL_ROLE_CLI" ] || [ -n "$INSTALL_MODE" ] || [ -n "$INSTALL_WORKERS" ] || [ -n "$INSTALL_MASTER_IP" ]; then
            fail "交互模式 (-i) 与 --role / --mode / --workers / --master-ip 不能同时使用"
        fi
        return
    fi

    if [ -n "$INSTALL_ROLE_CLI" ]; then
        case "$INSTALL_ROLE_CLI" in
            master|worker) ;;
            *) fail "--role 必须是 master 或 worker" ;;
        esac
    fi

    if [ -n "$INSTALL_MODE" ]; then
        case "$INSTALL_MODE" in
            single|multi) ;;
            *) fail "--mode 必须是 single 或 multi" ;;
        esac
    fi

    local role="${INSTALL_ROLE_CLI:-master}"
    if [ "$role" = "worker" ] && { [ -n "$INSTALL_MODE" ] || [ -n "$INSTALL_WORKERS" ]; }; then
        fail "worker 节点不支持 --mode 或 --workers"
    fi

    if [ -n "$INSTALL_MASTER_IP" ]; then
        {
            valid_ipv4 "$INSTALL_MASTER_IP" && [ "$INSTALL_MASTER_IP" != "localhost" ]
        } || fail "--master-ip 必须是有效的 IPv4 地址"
        if [ "${INSTALL_ROLE_CLI:-master}" != "worker" ]; then
            fail "--master-ip 仅能与 --role worker 一起使用"
        fi
    fi

    if [ -n "$INSTALL_WORKERS" ] && [ -z "$INSTALL_MODE" ]; then
        INSTALL_MODE=multi
    fi

    if [ "${INSTALL_MODE:-single}" = "multi" ] && [ -z "$INSTALL_WORKERS" ]; then
        fail "多机部署 (--mode multi) 必须通过 --workers 指定 worker IP 列表"
    fi

    if [ "${INSTALL_MODE:-single}" = "single" ] && [ -n "$INSTALL_WORKERS" ]; then
        fail "单机部署 (--mode single) 不能指定 --workers"
    fi
}

ACTION="${1:-help}"
if [ $# -gt 0 ]; then
    shift
fi

INTERACTIVE=0
CLEAN=0
INSTALL_ROLE_CLI=""
INSTALL_MODE=""
INSTALL_WORKERS=""
INSTALL_MASTER_IP=""
UP_MODELS_JSON=""
UP_MODELS_FILE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --interactive|-i)
            INTERACTIVE=1
            shift
            ;;
        --clean)
            CLEAN=1
            shift
            ;;
        --role)
            [ -n "${2:-}" ] || fail "--role 需要参数: master 或 worker"
            INSTALL_ROLE_CLI="$2"
            shift 2
            ;;
        --mode)
            [ -n "${2:-}" ] || fail "--mode 需要参数: single 或 multi"
            INSTALL_MODE="$2"
            shift 2
            ;;
        --workers)
            [ -n "${2:-}" ] || fail "--workers 需要逗号分隔的 IP 列表"
            INSTALL_WORKERS="$2"
            shift 2
            ;;
        --master-ip)
            [ -n "${2:-}" ] || fail "--master-ip 需要 master 节点 IP 地址"
            INSTALL_MASTER_IP="$2"
            shift 2
            ;;
        --models)
            [ -n "${2:-}" ] || fail "--models 需要 JSON 字符串参数"
            UP_MODELS_JSON="$2"
            shift 2
            ;;
        --models-file)
            [ -n "${2:-}" ] || fail "--models-file 需要文件路径参数"
            UP_MODELS_FILE="$2"
            shift 2
            ;;
        *)
            fail "未知参数: $1"
            ;;
    esac
done

if [ "$ACTION" = "install" ]; then
    validate_install_cli
fi

# install 时：若不在目标目录则拷贝过去再执行
if [ "$ACTION" = "install" ] && [ "$DEPLOY_DIR" != "$INSTALL_DIR" ]; then
    mkdir -p "$INSTALL_DIR" || fail "无法创建目标目录: $INSTALL_DIR"
    log "拷贝 deploy 目录到 $INSTALL_DIR ..."
    cp -a "$DEPLOY_DIR"/. "$INSTALL_DIR"/

    DEPLOY_DIR="$INSTALL_DIR"
    NE_DIR="${DEPLOY_DIR}/node-exporter"
    NPU_DIR="${DEPLOY_DIR}/npu-exporter"
    ALLOY_DIR="${DEPLOY_DIR}/alloy"

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
        echo "  install   安装（默认非交互、单机 master；自动检测 IP 生成 .env，并拷贝到 ~/.agentos/.agent-manager）"
        echo "  uninstall 卸载：停止服务 + 注销 systemd（默认保留数据和 .env）"
        echo "  up        启动：更新 exporter 配置 → 启动服务"
        echo "  down      停止：docker compose → node/npu_exporter（反序）"
        echo "  restart   重启：down → up"
        echo "  status    查看服务状态"
        echo ""
        echo "注意: up/down/restart/status/uninstall 需在安装目录 ~/.agentos/.agent-manager 下执行"
        echo ""
        echo "选项:"
        echo "  --interactive, -i  交互式安装（可选 master/worker、多机监控；与下方拓扑参数互斥）"
        echo "  --clean            uninstall 时删除数据卷、.env 和安装目录"
        echo ""
        echo "install 拓扑参数（非交互，与 -i 互斥）:"
        echo "  --role master|worker   节点角色，默认 master"
        echo "  --mode single|multi    仅 master；默认 single；仅传 --workers 时自动设为 multi"
  	    echo "  --workers ip1,ip2,...  master 多机 worker IPv4；可单独传参，或 --mode multi 时必填"
        echo "  --master-ip <ip>       仅 --role worker；master 节点 IP（用于 Alloy 日志上报）"
        echo ""
        echo "up 选项:"
        echo "  --models '<JSON>'      手动指定模型配置 JSON（含 api_base，自包含，无需配 .env）"
        echo "  --models-file <path>   从文件读取模型配置 JSON"
        echo ""
        echo "手动配置 JSON 格式:"
        echo '  {"api_base":"http://IP:PORT/v1","api_key":"sk-xxx","models":[{...},...]}'
        echo "  字段说明:"
        echo "    api_base      必填，推理服务地址（含 /v1）"
        echo "    api_key       可选，推理服务鉴权 Key"
        echo "    models        必填，模型列表"
        echo "      为空时嗅探该推理服务所有模型"
        echo "      有内容时只校验+补全列出的模型，每项含："
        echo "        id            可选，模型标识名（填了校验该模型存在，不填无意义）"
        echo "        max_model_len 可选，上下文长度（填了与嗅探值校验，不填用嗅探值补全）"
        echo "        owned_by      可选，部署框架（填了与嗅探值校验，不填用嗅探值补全）"
        echo "  手动模式会用 api_base 嗅探校验，没填的字段用嗅探值补全，填了的不一致会报错"
        echo ""
        echo "install 示例:"
        echo "  sudo bash $0 install                                          # 单机 master"
        echo "  sudo bash $0 install --workers 192.168.1.11,192.168.1.12"
        echo "  sudo bash $0 install --mode multi --workers 192.168.1.11,192.168.1.12"
        echo "  sudo bash $0 install --role worker --master-ip 192.168.1.10"
        echo ""
        echo "up 示例:"
        echo "  # 1. 用 .env 已有配置或嗅探"
        echo "  sudo bash $0 up"
        echo ""
        echo "  # 2. 命令行传 JSON（单引号包裹，内部双引号转义）"
        echo "  #    嗅探所有模型"
        echo "  sudo bash $0 up --models '{\"api_base\":\"http://192.168.1.10:8000/v1\",\"models\":[]}'"
        echo ""
        echo "  #    指定模型 + 补全字段"
        echo "  sudo bash $0 up --models '{\"api_base\":\"http://192.168.1.10:8000/v1\",\"api_key\":\"sk-xxx\",\"models\":[{\"id\":\"qwen2.5-72b\",\"max_model_len\":32768}]}'"
        echo ""
        echo "  # 3. 从文件读 JSON（推荐，无需转义）"
        echo "  sudo bash $0 up --models-file /path/to/models.json"
        echo ""
        echo "models.json 文件示例:"
        echo '  {'
        echo '    "api_base": "http://192.168.1.10:8000/v1",'
        echo '    "api_key": "sk-xxx",'
        echo '    "models": ['
        echo '      {"id": "qwen2.5-72b", "max_model_len": 32768, "owned_by": "vllm"},'
        echo '      {"id": "glm5.2", "max_model_len": 1048576, "owned_by": "sglang"},'
        echo '      {"id": "deepseek-v3"}'
        echo '    ]'
        echo '  }'
        echo ""
        echo '  # models 为空 → 嗅探所有模型'
        echo '  {"api_base": "http://192.168.1.10:8000/v1", "models": []}'
        exit 1
        ;;
esac
