#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# skillhub.sh — SkillHub 部署脚本（独立可执行，离线模式）
#
# 用法:
#   bash skillhub.sh install     # 初始化 .env + 校验镜像存在
#   bash skillhub.sh up          # 启动 docker compose + 健康检查 + 预装 skill 导入
#   bash skillhub.sh down        # 停止 docker compose（保留数据卷）
#   bash skillhub.sh uninstall   # 停止（保留数据卷）
#   bash skillhub.sh uninstall --clean   # 停止并删除数据卷
#   bash skillhub.sh status      # 健康检查
#
# 被 control-panel/deploy/deploy.sh 在 --with-skillhub 时调用。
# 部署态：编排+模板+镜像包+预装skill包均位于 ${SCRIPT_DIR}（skillhub/ 目录，由 AgentOS-Manager.tgz 解包提供）。
# 离线模式：不构建镜像、不拉取镜像，仅校验镜像存在（不存在则报错）。
# ============================================================

# ── 路径 ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SKILLHUB_FRONTEND_PORT="${SKILLHUB_FRONTEND_PORT:-8098}"
AGENTOS_PORT="${AGENTOS_PORT:-8090}"

# ── SkillHub 镜像列表（与 docker-compose.yml 中的 image: 保持一致） ──
SKILLHUB_IMAGES=(
    "skillhub-backend:latest"
    "skillhub-frontend:latest"
    "mysql:8.0"
    "redis:7-alpine"
    "minio/minio:RELEASE.2025-09-07T16-13-09Z"
    "minio/mc:RELEASE.2025-08-13T08-35-41Z"
)

# ── 日志 ──
log()  { echo "[skillhub] $*" >&2; }
fail() { echo "[skillhub] ERROR: $*" >&2; exit 1; }

# ── 获取宿主机 IP ──
detect_host_ip() {
    local ip
    ip=$(ip -o -4 route get 1 2>/dev/null | awk '{print $7}')
    [ -n "$ip" ] && echo "$ip" || echo "127.0.0.1"
}

_skillhub_host_ip() {
    echo "${SKILLHUB_HOST:-$(detect_host_ip)}"
}

# ── skillhub 目录定位 ──
# skillhub.sh 自身所在目录即 skillhub 部署目录（含 .env.example + docker/ + 镜像包）
_skillhub_dir() {
    echo "${SCRIPT_DIR}"
}

_skillhub_compose() {
    local d="$(_skillhub_dir)"
    [ -n "$d" ] && echo "${d}/docker/docker-compose.yml" || echo ""
}

_skillhub_env() {
    local d="$(_skillhub_dir)"
    [ -n "$d" ] && echo "${d}/.env" || echo ""
}

_available() {
    local compose="$(_skillhub_compose)"
    if [ ! -f "$compose" ]; then
        log "未找到 compose 文件: $compose，跳过"
        return 1
    fi
    return 0
}

# ── .env 初始化 ──
init_env() {
    local env_file="$(_skillhub_env)"
    local skillhub_dir="$(_skillhub_dir)"

    if [ -f "$env_file" ]; then
        log "  .env 已存在，跳过初始化"
        return 0
    fi

    local example="${skillhub_dir}/.env.example"
    [ -f "$example" ] || fail "未找到 .env.example: $example"

    cp "$example" "$env_file"

    local host_ip
    host_ip="$(_skillhub_host_ip)"

    # compose environment 块已覆盖 DB_HOST/DB_PORT/DB_USER/REDIS_HOST/REDIS_PORT/STORE_HOST/STORE_PORT
    # .env 只需提供 compose 不覆盖的配置 + 密钥
    sed -i "s/^MARKET_DEBUG=.*/MARKET_DEBUG=false/" "$env_file"
    sed -i "s/^STORE_DB_NAME=.*/STORE_DB_NAME=openjiuwen_market/" "$env_file"
    sed -i "s/^SYSTEM_ADMIN_USER=.*/SYSTEM_ADMIN_USER=system_admin/" "$env_file"
    sed -i "s/^STORAGE_TYPE=.*/STORAGE_TYPE=MinIO/" "$env_file"
    sed -i "s/^MARKET_BUCKET_NAME=.*/MARKET_BUCKET_NAME=openjiuwen-market-test/" "$env_file"
    sed -i "s/^MARKET_SKILL_REVIEW_ENABLED=.*/MARKET_SKILL_REVIEW_ENABLED=false/" "$env_file"

    # Skill 审核 LLM 模型配置（从 control-panel .env 读 LiteLLM 连接信息）
    local cp_env="${DEPLOY_DIR}/.env"
    local llm_host="" llm_key="" oauth_secret="" admin_user=""
    if [ -f "$cp_env" ]; then
        llm_host=$(grep "^LITELLM_HOST=" "$cp_env" | head -1 | cut -d= -f2-)
        llm_key=$(grep "^LITELLM_MASTER_KEY=" "$cp_env" | head -1 | cut -d= -f2-)
        # OAuth2 客户端密钥与 control-panel 保持一致（由 deploy.sh 生成随机值）
        oauth_secret=$(grep "^OAUTH2_CLIENT_SECRET=" "$cp_env" | head -1 | cut -d= -f2-)
        # 审核管理员用户名与 agent-os 管理员保持一致
        admin_user=$(grep "^AGENTOS_ADMIN_USERNAME=" "$cp_env" | head -1 | cut -d= -f2-)
    fi
    llm_host="${llm_host:-$host_ip}"
    admin_user="${admin_user:-admin}"

    # 审核管理员用户名匹配 agent-os 管理员（默认 admin）
    sed -i "s/^# *MARKET_REVIEW_ADMIN_USERNAMES=.*/MARKET_REVIEW_ADMIN_USERNAMES=${admin_user}/" "$env_file"
    grep -q "^MARKET_REVIEW_ADMIN_USERNAMES=" "$env_file" || echo "MARKET_REVIEW_ADMIN_USERNAMES=${admin_user}" >> "$env_file"
    sed -i "s|^MARKET_SKILL_REVIEW_MODEL_BASE_URL=.*|MARKET_SKILL_REVIEW_MODEL_BASE_URL=http://${llm_host}:8100|" "$env_file"
    sed -i "s/^MARKET_SKILL_REVIEW_MODEL_API_KEY=.*/MARKET_SKILL_REVIEW_MODEL_API_KEY=${llm_key}/" "$env_file"
    sed -i "s/^MARKET_SKILL_REVIEW_MODEL_NAME=.*/MARKET_SKILL_REVIEW_MODEL_NAME=gpt-4o/" "$env_file"
    # SKILLHUB_FRONTEND_PORT 已在预修改的 .env.example 中改好，此处只设值
    sed -i "s/^SKILLHUB_FRONTEND_PORT=.*/SKILLHUB_FRONTEND_PORT=${SKILLHUB_FRONTEND_PORT}/" "$env_file"
    sed -i "s/^FRONTEND_UPSTREAM_BACKEND_PORT=.*/FRONTEND_UPSTREAM_BACKEND_PORT=8100/" "$env_file"
    sed -i "s/^PLAYGROUND_ENABLED=.*/PLAYGROUND_ENABLED=false/" "$env_file"

    # backend 宿主机端口：默认 8100 与 control-panel LiteLLM 冲突，改用 8300
    # compose environment 块将容器内 STORE_PORT 固定为 8100，仅宿主机映射端口变 8300
    sed -i "s/^STORE_PORT=.*/STORE_PORT=8300/" "$env_file"

    # MinIO: 部署态用 host_ip（compose 端口映射 0.0.0.0:8099:8099，浏览器预签名 URL 需可达）
    sed -i "s/^MINIO_API_PORT=.*/MINIO_API_PORT=8099/" "$env_file"
    sed -i "s|^MARKET_S3_ENDPOINT=.*|MARKET_S3_ENDPOINT=http://${host_ip}:8099|" "$env_file"
    sed -i "s|^MARKET_OAUTH_FRONTEND_ORIGIN=.*|MARKET_OAUTH_FRONTEND_ORIGIN=http://${host_ip}:${SKILLHUB_FRONTEND_PORT}|" "$env_file"

    # 密钥
    local db_pass s3_ak s3_sk admin_token
    db_pass="${DB_PASSWORD:-$(openssl rand -hex 16)}"
    # MinIO 根用户（MINIO_ROOT_USER）限制 3-32 字符，hex 12 = 24 字符留出余量
    s3_ak="${MARKET_S3_ACCESS_KEY:-$(openssl rand -hex 12)}"
    s3_sk="${MARKET_S3_SECRET_KEY:-$(openssl rand -hex 16)}"
    admin_token="${SYSTEM_ADMIN_TOKEN:-sk-$(openssl rand -hex 24)}"

    sed -i "s/^DB_PASSWORD=.*/DB_PASSWORD=${db_pass}/" "$env_file"
    sed -i "s/^MARKET_S3_ACCESS_KEY=.*/MARKET_S3_ACCESS_KEY=${s3_ak}/" "$env_file"
    sed -i "s/^MARKET_S3_SECRET_KEY=.*/MARKET_S3_SECRET_KEY=${s3_sk}/" "$env_file"
    sed -i "s/^SYSTEM_ADMIN_TOKEN=.*/SYSTEM_ADMIN_TOKEN=${admin_token}/" "$env_file"

    # OAuth2 (AgentOS SSO) — 浏览器侧和容器侧都用 host_ip
    # control-panel 在独立 compose，skillhub backend 经宿主机端口访问
    sed -i "s/^MARKET_AGENTOS_OAUTH_ENABLED=.*/MARKET_AGENTOS_OAUTH_ENABLED=true/" "$env_file"
    sed -i "s/^MARKET_AGENTOS_OAUTH_CLIENT_ID=.*/MARKET_AGENTOS_OAUTH_CLIENT_ID=skillhub/" "$env_file"
    sed -i "s/^MARKET_AGENTOS_OAUTH_CLIENT_SECRET=.*/MARKET_AGENTOS_OAUTH_CLIENT_SECRET=${oauth_secret}/" "$env_file"
    sed -i "s|^MARKET_AGENTOS_OAUTH_REDIRECT_URI=.*|MARKET_AGENTOS_OAUTH_REDIRECT_URI=http://${host_ip}:${SKILLHUB_FRONTEND_PORT}/api/v1/auth/oauth/agentos/callback|" "$env_file"
    sed -i "s|^MARKET_AGENTOS_OAUTH_AUTHORIZE_URL=.*|MARKET_AGENTOS_OAUTH_AUTHORIZE_URL=http://${host_ip}:${AGENTOS_PORT}/api/v1/oauth2/authorize|" "$env_file"
    sed -i "s|^MARKET_AGENTOS_OAUTH_TOKEN_URL=.*|MARKET_AGENTOS_OAUTH_TOKEN_URL=http://${host_ip}:${AGENTOS_PORT}/api/v1/oauth2/token|" "$env_file"
    sed -i "s|^MARKET_AGENTOS_AUTH_USER_API_URL=.*|MARKET_AGENTOS_AUTH_USER_API_URL=http://${host_ip}:${AGENTOS_PORT}/api/v1/oauth2/userinfo|" "$env_file"

    log "  .env 已生成（端口 ${SKILLHUB_FRONTEND_PORT}，OAuth2 → ${host_ip}:${AGENTOS_PORT}）"
}

# ── 健康检查 ──
wait_healthy() {
    local url="http://127.0.0.1:${SKILLHUB_FRONTEND_PORT}"
    log "  等待后端就绪 ..."
    local i
    for i in $(seq 1 60); do
        if curl -sf "${url}/api/health" >/dev/null 2>&1; then
            log "  后端已就绪（第 ${i} 次探测）"
            return 0
        fi
        sleep 2
    done
    fail "后端 120s 内未就绪，查看日志: docker compose -f $(_skillhub_compose) logs backend"
}

# ── 预装 skill 导入 ──
upload_presets() {
    local upload_script="${SCRIPT_DIR}/upload-preset-skills.sh"
    # zip 路径优先从环境变量 PRESET_SKILLS_ZIP 获取，fallback 到同目录下的 preset-skills.zip
    local zip_file="${PRESET_SKILLS_ZIP:-${SCRIPT_DIR}/preset-skills.zip}"

    [ -f "$upload_script" ] || {
        log "  upload-preset-skills.sh 不存在，跳过"
        return 0
    }
    [ -f "$zip_file" ] || {
        log "  preset-skills.zip 不存在（路径: $zip_file），跳过。可通过 PRESET_SKILLS_ZIP 环境变量指定路径"
        return 0
    }

    local token
    token="$(grep -E '^SYSTEM_ADMIN_TOKEN=' "$(_skillhub_env)" 2>/dev/null | head -1 | cut -d= -f2-)"
    [ -n "$token" ] || {
        log "  未读取到 SYSTEM_ADMIN_TOKEN，跳过"
        return 0
    }

    log "  导入预置 skill ..."
    if SKILLHUB_URL="http://127.0.0.1:${SKILLHUB_FRONTEND_PORT}" \
       SYSTEM_ADMIN_TOKEN="$token" \
       bash "$upload_script" "$zip_file"; then
        PRESET_UPLOAD_OK=1
    else
        PRESET_UPLOAD_OK=0
        log "  WARNING: 预装 skill 导入失败（不影响运行）"
    fi
}

# ── 镜像检测（离线模式：不构建、不拉取，不存在则报错） ──
check_images() {
    local missing=()

    for img in "${SKILLHUB_IMAGES[@]}"; do
        if docker image inspect "$img" &>/dev/null; then
            log "  $img — OK"
        else
            log "  $img — 不存在"
            missing+=("$img")
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        log "ERROR: 以下镜像不存在（离线模式不自动构建/拉取）："
        for img in "${missing[@]}"; do
            log "  - $img"
        done
        log "请先手动 docker load 或 docker pull 导入所需镜像，再重新执行部署。"
        return 1
    fi
    log "所有 skillhub 镜像已就绪。"
    return 0
}

# ── 命令实现 ──

cmd_install() {
    _available || return 0
    log "install (init env + check images)"
    command -v docker >/dev/null 2>&1 || fail "未找到 docker"

    init_env

    # 离线模式：校验镜像存在，不存在则报错（不构建、不拉取、不加载）
    check_images || fail "镜像校验失败，请先手动 docker load 或 docker pull 导入所需镜像"

    log "  install finished"
}

cmd_up() {
    _available || return 0
    command -v docker >/dev/null 2>&1 || fail "未找到 docker"
    docker compose version >/dev/null 2>&1 || fail "未找到 docker compose v2"

    init_env

    # 离线模式：校验镜像存在，不存在则报错（不构建、不拉取、不加载）
    check_images || fail "镜像校验失败，请先手动 docker load 或 docker pull 导入所需镜像"

    local d="$(_skillhub_dir)"
    log "up (docker compose up)"
    # 从 docker/ 目录执行，使 compose 内 env_file: ../.env 解析到 skillhub/.env
    # --no-build: 离线模式，镜像不存在直接报错（不尝试构建）
    (
        cd "${d}/docker"
        docker compose -f docker-compose.yml --env-file ../.env up -d --no-build
    )
    wait_healthy
    upload_presets

    echo ""
    echo "  ================ SkillHub 已启动 ================"
    if [ "${PRESET_UPLOAD_OK:-0}" -eq 1 ]; then
        echo "  预装 skill: 已导入"
    else
        echo "  ⚠ 预装 skill: 未导入（可手动执行 upload-preset-skills.sh）"
    fi
}

cmd_down() {
    _available || return 0
    local d="$(_skillhub_dir)"
    log "down"
    (
        cd "${d}/docker"
        docker compose -f docker-compose.yml --env-file ../.env down
    )
    log "  stopped（数据保留在 named volume）"
}

cmd_uninstall() {
    _available || return 0
    [ -f "$(_skillhub_env)" ] || { log "  .env 不存在，跳过"; return 0; }
    local d="$(_skillhub_dir)"
    if [ "${1:-}" = "--clean" ]; then
        log "uninstall (down -v)"
        (
            cd "${d}/docker"
            docker compose -f docker-compose.yml --env-file ../.env down -v
        )
        log "  uninstalled (volumes removed)"
    else
        log "uninstall (down)"
        (
            cd "${d}/docker"
            docker compose -f docker-compose.yml --env-file ../.env down
        )
        log "  uninstalled (data volumes retained)"
    fi
}

cmd_status() {
    _available || return 0
    local url="http://$(_skillhub_host_ip):${SKILLHUB_FRONTEND_PORT}"
    if curl --connect-timeout 3 --max-time 5 -sf "${url}/api/health" >/dev/null 2>&1; then
        echo "  [OK]   skillhub         (:${SKILLHUB_FRONTEND_PORT})"
    else
        echo "  [--]   skillhub         (:${SKILLHUB_FRONTEND_PORT})"
    fi
}

# ── 入口 ──
case "${1:-}" in
    install)   cmd_install ;;
    up)        cmd_up ;;
    down)      cmd_down ;;
    restart)   cmd_down; cmd_up ;;
    uninstall) cmd_uninstall "${2:-}" ;;
    status)    cmd_status ;;
    *)
        echo "用法: bash $0 <command>"
        echo ""
        echo "命令:"
        echo "  install    初始化 .env + 校验镜像存在（离线模式，不构建/拉取）"
        echo "  up         启动 + 健康检查 + 预装 skill 导入（离线模式，--no-build）"
        echo "  down       停止（保留数据卷）"
        echo "  restart    重启（down + up）"
        echo "  uninstall  停止（保留数据卷）"
        echo "  uninstall --clean  停止 + 删除数据卷"
        echo "  status     健康检查"
        exit 1
        ;;
esac
