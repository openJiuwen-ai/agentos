#!/usr/bin/env bash
set -euo >/dev/null 2>&1

# ============================================================
# agentos 统一部署脚本（可插拔架构）
#
# 设计说明:
#   每个组件模块在 deploy/<module>/ 下放一个 module.sh，实现 4 个钩子函数:
#     <module>_up / <module>_down / <module>_install / <module>_uninstall
#   本脚本负责加载所有 module.sh，并按 MODULES 数组声明的顺序统一调度。
#   新增模块只需:
#     1. 在 deploy/ 下新建 <module>/ 目录，放入 module.sh 和所需配置文件
#     2. 在 MODULES 数组中添加模块名
#
# 执行顺序:
#   up:        按 MODULES 声明顺序
#   down:      逆序
#   install:   按 MODULES 声明顺序
#   uninstall: 逆序
#
# 用法:
#   ./agentos.sh up --hosts 192.168.1.1,192.168.1.2
#   ./agentos.sh down --hosts 192.168.1.1,192.168.1.2
#   ./agentos.sh install
#   ./agentos.sh uninstall
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTOS_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ===== 模块注册（按部署/安装顺序声明，down/uninstall 自动逆序） =====
MODULES=("jiuwenbox" "yuanrong" "agent-gateway" "jiuwenswarm")

# ===== 全局环境变量 =====
YR_PYTHON_VERSION="${YR_PYTHON_VERSION:-3.11}"

# ===== agent SSH 直连密钥路径（用户自行生成，脚本不生成；默认 /root/.ssh 下）=====
# 简便模式：host/backend/client 三处共用同一套密钥。生产环境建议三套独立
export AGENTOS_SSH_KEY="${AGENTOS_SSH_KEY:-/root/.ssh/agent_key}"
export AGENTOS_SSH_BACKEND_PUBLIC_DIR="${AGENTOS_SSH_BACKEND_PUBLIC_DIR:-/root/.ssh/agent_pub}"

# ===== 日志函数 =====
info()    { echo -e "\033[36m=== $@ ===\033[0m"; }
success() { echo -e "\033[32m✅ $@\033[0m"; }
warning() { echo -e "\033[33m⚠️  $@\033[0m"; }
error()   { echo -e "\033[31m❌ $@\033[0m"; exit 1; }

# ===== 加载所有模块 =====
load_modules() {
    local mod
    for mod in "${MODULES[@]}"; do
        local mod_file="${SCRIPT_DIR}/${mod}/module.sh"
        if [ ! -f "${mod_file}" ]; then
            error "Module file not found: ${mod_file}"
        fi
        # shellcheck source=/dev/null
        source "${mod_file}"
        info "Loaded module: ${mod}"
    done
}

# ===== 反转数组（用于 down/uninstall 逆序） =====
reverse_modules() {
    local reversed=()
    local i
    for ((i=${#MODULES[@]}-1; i>=0; i--)); do
        reversed+=("${MODULES[$i]}")
    done
    echo "${reversed[@]}"
}

# ===== 调度引擎：遍历模块，调用对应钩子 =====
run_hooks() {
    local hook="$1"  # up / down / install / uninstall
    local sub_args
    sub_args=$(build_sub_args)

    local module_list
    if [ "${hook}" = "down" ] || [ "${hook}" = "uninstall" ]; then
        # down/uninstall 逆序
        module_list=$(reverse_modules)
    else
        module_list="${MODULES[@]}"
    fi

    local total=${#MODULES[@]}
    local idx=0
    for mod in ${module_list}; do
        idx=$((idx+1))
        local fn="${mod}_${hook}"
        if ! declare -f "${fn}" >/dev/null 2>&1; then
            warning "Module '${mod}' has no '${hook}' hook, skipping"
            continue
        fi
        echo ""
        info "[${idx}/${total}] ${mod} ${hook}"
        "${fn}" ${sub_args}
        success "${mod} ${hook} finished"
    done
}

# ===== 参数解析 =====
CMD=""
CLUSTER_HOSTS=""
EXTRA_ARGS=()

parse_args() {
    local i=0
    local args=("$@")

    while [ $i -lt ${#args[@]} ]; do
        case "${args[$i]}" in
            up|down|restart|install|uninstall)
                CMD="${args[$i]}"
                i=$((i+1))
                ;;
            --hosts)
                CLUSTER_HOSTS="${args[$((i+1))]}"
                i=$((i+2))
                ;;
            -h|--help)
                print_help
                ;;
            *)
                EXTRA_ARGS+=("${args[$i]}")
                i=$((i+1))
                ;;
        esac
    done

    if [ -z "${CMD}" ]; then
        error "Command not specified! Use 'up', 'down', 'restart', 'install' or 'uninstall'"
    fi
}

# ===== 构造传给子脚本的参数 =====
build_sub_args() {
    local sub_args=()
    if [ -n "${CLUSTER_HOSTS}" ]; then
        sub_args+=("--hosts" "${CLUSTER_HOSTS}")
    fi
    sub_args+=("${EXTRA_ARGS[@]}")
    echo "${sub_args[@]}"
}

# ===== 将 deploy 目录持久化到 ~/.agentos =====
# install 后用户会删除安装包与解压目录，但后续 up/down/uninstall 仍需 deploy 脚本，
# 故在 install 流程中先把整个 deploy 目录拷贝到 ~/.agentos/ 下保留。
_persist_deploy_dir() {
    local persist_root="${HOME:-/root}/.agentos"
    local persist_dir="${persist_root}/deploy"
    mkdir -p "${persist_root}"
    rm -rf "${persist_dir}"
    cp -a "${SCRIPT_DIR}" "${persist_dir}"
    info "Persisted deploy directory to ${persist_dir}"
}

# ===== agentos 用户保障（宿主大前提）=====
# up 时对每台目标主机确保 agentos 用户存在（已存在则跳过，否则 useradd agentos）。
# 任一台失败即打断 up（agentos 用户是沙箱默认 policy 的运行用户，缺失会导致沙箱起不来）。
ensure_agentos_user() {
    info "Ensuring agentos user"
    local targets="${CLUSTER_HOSTS}"
    [ -z "${targets}" ] && targets="127.0.0.1"
    local host
    local IFS=','
    for host in ${targets}; do
        host="$(echo "${host}" | tr -d '[:space:]')"
        [ -z "${host}" ] && continue
        if [ "${host}" = "127.0.0.1" ] || [ "${host}" = "localhost" ]; then
            bash -c 'id -u agentos >/dev/null 2>&1 || useradd agentos' \
                || error "Failed to create agentos user on ${host}"
        else
            ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "root@${host}" \
                'id -u agentos >/dev/null 2>&1 || useradd agentos' \
                || error "Failed to create agentos user on ${host}"
        fi
    done
}

# ===== 命令入口 =====
deploy_up() {
    echo ""
    info "Starting full deployment (up)"
    ensure_agentos_user
    info "Modules: ${MODULES[*]}"
    if [ -n "${CLUSTER_HOSTS}" ]; then
        info "Cluster hosts: ${CLUSTER_HOSTS}"
    fi
    run_hooks up
    _print_summary up
}

deploy_down() {
    echo ""
    info "Starting full teardown (down)"
    info "Modules (reverse): $(reverse_modules)"
    if [ -n "${CLUSTER_HOSTS}" ]; then
        info "Cluster hosts: ${CLUSTER_HOSTS}"
    fi
    run_hooks down
    _print_summary down
}

deploy_restart() {
    deploy_down
    echo ""
    deploy_up
}

deploy_install() {
    echo ""
    info "Starting full install (local only)"
    info "Modules: ${MODULES[*]}"
    info "Python version: ${YR_PYTHON_VERSION}"
    # 先把 deploy 目录持久化到 ~/.agentos/deploy，避免安装包/解压目录被删除后无法 up/down
    _persist_deploy_dir
    run_hooks install
    _print_summary install
}

deploy_uninstall() {
    echo ""
    info "Starting full uninstall (local only)"
    info "Modules (reverse): $(reverse_modules)"
    info "Python version: ${YR_PYTHON_VERSION}"
    run_hooks uninstall
    _print_summary uninstall
}

_print_summary() {
    local cmd="$1"
    echo ""
    success "Full ${cmd} completed!"
    echo "=========================================="
    if [ "${cmd}" = "up" ] || [ "${cmd}" = "down" ] || [ "${cmd}" = "restart" ]; then
        if [ "${cmd}" = "down" ]; then
            echo "  Order: $(reverse_modules)"
        else
            echo "  Order: ${MODULES[*]}"
        fi
        if [ -n "${CLUSTER_HOSTS}" ]; then
            echo "  Hosts: ${CLUSTER_HOSTS}"
        fi
    else
        echo "  Packages: ${MODULES[*]}"
        echo "  Whl source: ${AGENTOS_ROOT}"
    fi
    echo "=========================================="
}

print_help() {
    cat << EOF
Usage: ./$(basename "$0") <COMMAND> [OPTIONS]

统一部署脚本（可插拔架构），按 MODULES 数组声明的顺序编排各组件部署。
当前已注册模块: ${MODULES[*]}
  up:      按声明顺序部署
  down:    逆序卸载
  install: 按声明顺序安装 whl 包
  uninstall: 逆序卸载 whl 包

Commands (Required):
  up          按顺序部署全部组件
  down        逆序停止并卸载全部组件
  restart     重启全部组件（先 down 再 up）
  install     在本机安装全部组件的 whl 包（不启动服务）
  uninstall   在本机卸载全部组件的 whl 包

Options:
  --hosts HOSTS   目标主机IP列表，逗号分隔。第一个IP为yr master节点，其余为agent节点
                  单机: --hosts 192.168.1.1
                  多机: --hosts 192.168.1.1,192.168.1.2,192.168.1.3
                  不指定时默认使用本机IP
  -h, --help      显示帮助信息

Config:
  jiuwenbox   配置文件: deploy/jiuwenbox/default-policy.yaml (含 extensions 目录占位符)
              jiuwenbox-server 随 jiuwenswarm whl 包安装，无需单独 install
  yuanrong    环境变量直接通过命令行/环境变量传入（见 yuanrong_deploy.sh -h）
              agent SSH 直连默认启用（简便模式：host/backend/client 混用一套密钥）：
                AGENTOS_SSH_KEY              私钥 (/root/.ssh/agent_key)，三处用途共用
                AGENTOS_SSH_BACKEND_PUBLIC_DIR 公钥目录 (/root/.ssh/agent_pub)，
                                              须含 authorized_keys；不能在 /etc 下
              密钥由用户自行生成（注意权限，sshd StrictModes 拒 group/other 可写）：
                ssh-keygen -t ed25519 -N '' -f /root/.ssh/agent_key
                mkdir -p /root/.ssh/agent_pub && cp /root/.ssh/agent_key.pub /root/.ssh/agent_pub/authorized_keys
                chmod 644 /root/.ssh/agent_pub/authorized_keys && chmod 755 /root/.ssh/agent_pub
  jiuwenswarm 配置文件: deploy/jiuwenswarm/.env.custom (基于 .env.example)
  whl 包来源  install 时从 agentos 根目录（deploy 的同级目录）读取

Prerequisites:
  - 部署机器到所有目标主机需配置 SSH 免密登录
  - 目标主机需预装指定版本的 Python
  - jiuwenbox 部署前需确保 jiuwenswarm whl 包已安装（jiuwenbox-server 入口随 jiuwenswarm 安装）
  - jiuwenswarm/gateway 部署前需确保 openyuanrong 已在所有目标主机上安装并启动

Examples:
  # 1. 本机安装全部 whl 包
  ./agentos.sh install

  # 2. 一键部署全部组件（单机）
  ./agentos.sh up --hosts 192.168.1.1

  # 3. 一键部署全部组件（多机，第一个IP为master）
  ./agentos.sh up --hosts 192.168.1.1,192.168.1.2,192.168.1.3

  # 4. 不指定 hosts，默认本机部署
  ./agentos.sh up

  # 5. 停止并卸载全部组件
  ./agentos.sh down --hosts 192.168.1.1,192.168.1.2

  # 6. 重启全部组件
  ./agentos.sh restart --hosts 192.168.1.1

  # 7. 指定其他 whl 目录安装 yuanrong
  YR_PKG_BASE=/data/yr_whls ./agentos.sh install

  # 8. 自定义 agent SSH 直连密钥路径（默认 /root/.ssh/ 下，需用户自行生成）
  AGENTOS_SSH_KEY=/path/my_key \
  AGENTOS_SSH_BACKEND_PUBLIC_DIR=/path/my_pub \
  ./agentos.sh up --hosts 192.168.1.1

扩展模块:
  新增组件只需两步:
  1. 在 deploy/ 下新建 <module>/ 目录，放入 module.sh（实现 <module>_up/down/install/uninstall 钩子）
  2. 在本脚本顶部 MODULES 数组中添加模块名

注意:
  - up/restart 不安装 whl 包，请先在各目标主机执行 install
  - jiuwenswarm 函数注册只在 yr master 节点（第一个IP）执行
  - gateway 依赖 jiuwenswarm 部署后产生的 FUNCTION_ID/FRONTEND_PORT，同一进程内自动传递
EOF
    exit 0
}

main() {
    if [ $# -eq 0 ]; then
        print_help
    fi
    load_modules
    parse_args "$@"
    case "${CMD}" in
        up)        deploy_up ;;
        down)      deploy_down ;;
        restart)   deploy_restart ;;
        install)   deploy_install ;;
        uninstall) deploy_uninstall ;;
        *)         error "Unknown command: ${CMD}" ;;
    esac
}

main "$@"
