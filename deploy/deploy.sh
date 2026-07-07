#!/usr/bin/env bash
set -euo >/dev/null 2>&1

# ============================================================
# agentos 统一部署脚本（编排式）
# 按固定顺序汇总各组件部署：
#   up:      1. openyuanrong 集群 -> 2. jiuwenswarm 函数 -> 3. gateway
#   down:    逆序卸载
#   restart: down -> up
# 用法:
#   ./deploy.sh up --hosts 192.168.1.1,192.168.1.2
#   ./deploy.sh down --hosts 192.168.1.1,192.168.1.2
#   ./deploy.sh restart --hosts 192.168.1.1,192.168.1.2
#   ./deploy.sh install            # 仅本机安装 yuanrong whl 包
#   ./deploy.sh uninstall          # 仅本机卸载 yuanrong whl 包
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTOS_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

YUANRONG_DEPLOY_DIR="${SCRIPT_DIR}/yuanrong"
JIUWENSWARM_DEPLOY_DIR="${AGENTOS_ROOT}/jiuwenswarm/deploy/yuanrong"
JIUWENSWARM_CONFIG_DIR="${SCRIPT_DIR}/jiuwenswarm"

# ===== 日志函数 =====
info()    { echo -e "\033[36m=== $@ ===\033[0m"; }
success() { echo -e "\033[32m✅ $@\033[0m"; }
warning() { echo -e "\033[33m⚠️  $@\033[0m"; }
error()   { echo -e "\033[31m❌ $@\033[0m"; exit 1; }

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
                # 未知参数原样透传给子脚本
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

# ===== 1. openyuanrong 集群部署 =====
run_yuanrong() {
    local yr_script="${YUANRONG_DEPLOY_DIR}/yuanrong_deploy.sh"
    if [ ! -f "${yr_script}" ]; then
        error "yuanrong deploy script not found: ${yr_script}"
    fi

    info "[1/2] Deploying openyuanrong cluster: ${yr_script} $*"
    bash "${yr_script}" "$@"
    success "openyuanrong cluster deployment finished"
}

# ===== 2. jiuwenswarm 函数 + gateway 部署 =====
# jiuwenswarm 的 deploy.sh 使用相对路径 source，必须在子模块的 deploy/yuanrong 目录下执行
# 配置文件统一放在 agentos/deploy/jiuwenswarm/.env.custom，执行前拷贝到子模块目录，执行后清理
run_jiuwenswarm() {
    local jw_script="${JIUWENSWARM_DEPLOY_DIR}/deploy.sh"
    if [ ! -f "${jw_script}" ]; then
        error "jiuwenswarm deploy script not found: ${jw_script}"
    fi

    local custom_env_src="${JIUWENSWARM_CONFIG_DIR}/.env.custom"
    local custom_env_dst="${JIUWENSWARM_DEPLOY_DIR}/.env.custom"
    local copied=false

    if [ -f "${custom_env_src}" ]; then
        if [ "$(realpath -m "${custom_env_src}" 2>/dev/null || echo "${custom_env_src}")" != \
           "$(realpath -m "${custom_env_dst}" 2>/dev/null || echo "${custom_env_dst}")" ]; then
            cp -f "${custom_env_src}" "${custom_env_dst}"
            copied=true
            info "Copied jiuwenswarm config: ${custom_env_src} -> ${custom_env_dst}"
        fi
    else
        warning "No .env.custom found at ${custom_env_src}, using defaults in submodule"
    fi

    info "[2/2] Deploying jiuwenswarm function + gateway in ${JIUWENSWARM_DEPLOY_DIR}: $*"
    (
        cd "${JIUWENSWARM_DEPLOY_DIR}"
        bash ./deploy.sh "$@"
    )
    success "jiuwenswarm function + gateway deployment finished"

    # 清理临时拷贝到子模块目录的配置文件，避免污染 submodule 工作区
    if [ "${copied}" = "true" ] && [ -f "${custom_env_dst}" ]; then
        rm -f "${custom_env_dst}"
        info "Cleaned up temporary config in submodule: ${custom_env_dst}"
    fi
}

# ===== 部署编排（按固定顺序） =====
deploy_up() {
    local sub_args
    sub_args=$(build_sub_args)

    echo ""
    info "Starting full deployment (up)"
    info "Order: 1.openyuanrong -> 2.jiuwenswarm(function) -> 3.gateway"
    if [ -n "${CLUSTER_HOSTS}" ]; then
        info "Cluster hosts: ${CLUSTER_HOSTS}"
    fi
    echo ""

    # 1. openyuanrong 集群
    run_yuanrong up ${sub_args}

    echo ""
    # 2 & 3. jiuwenswarm 函数 + gateway（submodule 脚本内部按 jiuwenswarm -> gateway 顺序执行）
    run_jiuwenswarm up ${sub_args}

    echo ""
    success "Full deployment (up) completed!"
    echo "=========================================="
    echo "  Order: openyuanrong -> jiuwenswarm -> gateway"
    if [ -n "${CLUSTER_HOSTS}" ]; then
        echo "  Hosts: ${CLUSTER_HOSTS}"
    fi
    echo "=========================================="
}

deploy_down() {
    local sub_args
    sub_args=$(build_sub_args)

    echo ""
    info "Starting full teardown (down)"
    info "Order: 1.gateway -> 2.jiuwenswarm(function) -> 3.openyuanrong (reverse)"
    if [ -n "${CLUSTER_HOSTS}" ]; then
        info "Cluster hosts: ${CLUSTER_HOSTS}"
    fi
    echo ""

    # 1 & 2. gateway + jiuwenswarm 函数（submodule 脚本内部按 gateway -> jiuwenswarm 逆序卸载）
    run_jiuwenswarm down ${sub_args}

    echo ""
    # 3. openyuanrong 集群
    run_yuanrong down ${sub_args}

    echo ""
    success "Full teardown (down) completed!"
    echo "=========================================="
    echo "  Order: gateway -> jiuwenswarm -> openyuanrong (reverse)"
    if [ -n "${CLUSTER_HOSTS}" ]; then
        echo "  Hosts: ${CLUSTER_HOSTS}"
    fi
    echo "=========================================="
}

deploy_restart() {
    deploy_down
    echo ""
    deploy_up
}

# install/uninstall 仅作用于 yuanrong whl 包（本机），不涉及 jiuwenswarm/gateway
deploy_install() {
    local sub_args
    sub_args=$(build_sub_args)
    info "Installing openyuanrong whl packages (local only)"
    run_yuanrong install ${sub_args}
}

deploy_uninstall() {
    local sub_args
    sub_args=$(build_sub_args)
    info "Uninstalling openyuanrong whl packages (local only)"
    run_yuanrong uninstall ${sub_args}
}

print_help() {
    cat << EOF
Usage: ./$(basename "$0") <COMMAND> [OPTIONS]

统一部署脚本，按固定顺序编排各组件部署：
  up:      1. openyuanrong 集群 -> 2. jiuwenswarm 函数 -> 3. gateway
  down:    逆序卸载（gateway -> jiuwenswarm -> openyuanrong）
  restart: down -> up

Commands (Required):
  up          按顺序部署全部组件（openyuanrong + jiuwenswarm + gateway）
  down        逆序停止并卸载全部组件
  restart     重启全部组件（先 down 再 up）
  install     仅在本机安装 openyuanrong whl 包（不启动服务，不需要 --hosts）
  uninstall   仅在本机卸载 openyuanrong whl 包（不需要 --hosts）

Options:
  --hosts HOSTS   目标主机IP列表，逗号分隔。第一个IP为yr master节点，其余为agent节点
                  单机: --hosts 192.168.1.1
                  多机: --hosts 192.168.1.1,192.168.1.2,192.168.1.3
                  不指定时默认使用本机IP
  -h, --help      显示帮助信息

Config:
  yuanrong    环境变量直接通过命令行/环境变量传入（见 yuanrong_deploy.sh -h）
  jiuwenswarm 配置文件: deploy/jiuwenswarm/.env.custom (基于 .env.example)

Prerequisites:
  - 部署机器到所有目标主机需配置 SSH 免密登录
  - 目标主机需预装指定版本的 Python
  - jiuwenswarm/gateway 部署前需确保 openyuanrong 已在所有目标主机上安装并启动

Examples:
  # 1. 本机安装 yuanrong whl 包
  ./deploy.sh install

  # 2. 一键部署全部组件（单机）
  ./deploy.sh up --hosts 192.168.1.1

  # 3. 一键部署全部组件（多机，第一个IP为master）
  ./deploy.sh up --hosts 192.168.1.1,192.168.1.2,192.168.1.3

  # 4. 不指定 hosts，默认本机部署
  ./deploy.sh up

  # 5. 停止并卸载全部组件
  ./deploy.sh down --hosts 192.168.1.1,192.168.1.2

  # 6. 重启全部组件
  ./deploy.sh restart --hosts 192.168.1.1

  # 7. 指定本地 whl 目录安装 yuanrong
  YR_PKG_BASE=/data/yr_whls ./deploy.sh install

注意:
  - up/restart 不安装 yuanrong whl 包，请先在各目标主机执行 install
  - jiuwenswarm 函数注册只在 yr master 节点（第一个IP）执行
  - gateway 依赖 jiuwenswarm 部署后产生的 FUNCTION_ID/FRONTEND_PORT，同一进程内自动传递
EOF
    exit 0
}

main() {
    if [ $# -eq 0 ]; then
        print_help
    fi
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
