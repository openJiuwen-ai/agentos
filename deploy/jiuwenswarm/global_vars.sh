#!/usr/bin/env bash
set -euo >/dev/null 2>&1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CUSTOM_ENV_FILE="${SCRIPT_DIR}/.env.custom"
ENV_FILE="${SCRIPT_DIR}/.env"

CLAW_META_PROCESS_TEMPLATE_FILE="${SCRIPT_DIR}/conf/claw_meta_process.template.json"
CLAW_META_PROCESS_FILE="${SCRIPT_DIR}/conf/claw_meta_process.json"

GATEWAY_CONFIG_TEMPLATE_FILE="${SCRIPT_DIR}/conf/gateway-config-yuanrong.template.yaml"
GATEWAY_CONFIG_FILE="${SCRIPT_DIR}/conf/gateway-config.yaml"
GATEWAY_ENV_FILE="${SCRIPT_DIR}/conf/gateway.env"

REG_FUNC_FILE="${SCRIPT_DIR}/../../jiuwenswarm/extensions/clawee.py"

META_PORT=""
CMD=""

declare -ga MODULES=()

declare -A DEPLOY_VARS=(
    ["FUNC_SVC_NAME"]="0@jiuwen@swarm"
    ["SANDBOX_TYPE"]=""
    ["MGR_CPU"]="300"
    ["MGR_MEMORY"]="600"
    ["MGR_MIN_INSTANCE"]="1"
    ["MGR_MAX_INSTANCE"]="10"
    ["MGR_CONCURRENT_NUM"]="10"
    ["CLUSTER_HOSTS"]=""
    ["YR_PYTHON_VERSION"]="3.11"
    ["YR_FUNC_CODE_DIR"]=""
    ["YR_SESSION_DIR"]=""
    ["JIUWENSWARM_PACKAGE_URL"]=""
    ["JIUWENSWARM_INSTANCE_NAME"]=""
    ["GATEWAY_CONCURRENCY"]="1"
    ["GATEWAY_INVOKE_TIMEOUT"]="60"
    ["GATEWAY_SESSION_MAP_SCOPE"]="per_chat_bot_user"
    ["MODEL_PROVIDER"]=""
    ["MODEL_NAME"]=""
    ["API_BASE"]=""
    ["API_KEY"]=""
    ["EMBED_API_KEY"]=""
    ["EMBED_API_BASE"]=""
    ["EMBED_MODEL"]=""
    ["FRONTEND_PORT"]=""
    ["FUNCTION_ID"]=""
    ["MASTER_NODE_IP"]=""
    ["OS_TYPE"]=""
    ["EXTENSION_DIRS"]=""
    # === web 一键拉起相关（2026-07-27 增）===
    # gateway 进程监听地址（app_gateway.py 读 os.getenv("GATEWAY_HOST","127.0.0.1")）
    # 默认 0.0.0.0 让外部可访问 TUI-WS 19001；设 127.0.0.1 则只本机
    ["GATEWAY_HOST"]="0.0.0.0"
    ["GATEWAY_PORT"]="19001"
    # WebChannel WS（gateway 内部，web 前端 proxy 目标，保持 127.0.0.1）
    ["WEB_PORT"]="19000"
    # web 前端静态服务监听地址（app_web.py 读 os.getenv("FRONTEND_HOST","localhost")）
    # 默认 0.0.0.0 让外部浏览器可访问 5173
    ["FRONTEND_HOST"]="0.0.0.0"
    # web 前端静态服务端口（区别于 yuanrong frontend 的 FRONTEND_PORT=8888）
    ["WEB_STATIC_PORT"]="5173"
    # 是否在 up 时一并拉起 web 前端（yes/no）
    ["WEB_ENABLED"]="yes"
)
