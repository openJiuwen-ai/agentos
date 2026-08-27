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
#   ./agentos.sh up
#   ./agentos.sh down
#   ./agentos.sh install
#   ./agentos.sh uninstall
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTOS_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ===== etcd 独立脚本（init/deinit 委托给它，agentos.sh 不重复实现 etcd 逻辑） =====
ETCD_SH="${SCRIPT_DIR}/etcd.sh"

# ===== 模块注册（按部署/安装顺序声明，down/uninstall 自动逆序） =====
MODULES=("moosefs" "jiuwenbox" "yuanrong" "agent-gateway" "jiuwenswarm")

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
        "${fn}" "${EXTRA_ARGS[@]}"
        success "${mod} ${hook} finished"
    done
}

# ===== 参数解析 =====
CMD=""
EXTRA_ARGS=()

parse_args() {
    local i=0
    local args=("$@")

    while [ $i -lt ${#args[@]} ]; do
        case "${args[$i]}" in
            up|down|restart|install|uninstall|init|deinit|status)
                CMD="${args[$i]}"
                i=$((i+1))
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
        error "Command not specified! Use 'install', 'init', 'up', 'down', 'status', 'deinit', 'uninstall' or 'restart'"
    fi
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
# up 时确保 agentos 用户存在（已存在则跳过，否则 useradd agentos）。
# 失败即打断 up（agentos 用户是沙箱默认 policy 的运行用户，缺失会导致沙箱起不来）。
ensure_agentos_user() {
    info "Ensuring agentos user"
    bash -c 'id -u agentos >/dev/null 2>&1 || useradd agentos' \
        || error "Failed to create agentos user"
}

# ===== up 前置检查：etcd 集群必须已就绪 =====
# init 与 up 拆开后，用户可能忘记先 init。这里显式探测 etcd 可达性，
# 不可达则明确报错引导先 init，而不是让 yuanrong 抛看不懂的连接失败。
ensure_etcd_ready() {
    info "Checking etcd availability (run 'agentos.sh init' first if this fails)"
    [ -r "${ETCD_SH}" ] || error "etcd script not found or not readable: ${ETCD_SH}"
    bash "${ETCD_SH}" check \
        || error "etcd not reachable. Run './agentos.sh init' on etcd nodes first, then retry 'up'."
}

# ===== 命令入口 =====
deploy_up() {
    echo ""
    info "Starting full deployment (up)"
    ensure_agentos_user
    ensure_etcd_ready
    info "Modules: ${MODULES[*]}"
    run_hooks up
    _print_summary up
}

# ===== init: bootstrap etcd（委托 etcd.sh clean + up，非 etcd 节点自动跳过） =====
# etcd 是全集群前置依赖，作为一次性 bootstrap 步骤独立于日常 up/down。
# 可在所有节点统一执行：仅 etcd_nodes 节点实际启动，其余为 no-op。
# 自动清理历史 etcd 数据（对齐 yr start 语义：每次 bootstrap 视为干净启动），
# 修改 etcd_nodes 拓扑后无需用户手动 clean 即可直接重新 bootstrap。
deploy_init() {
    echo ""
    info "Initializing etcd (bootstrap)"
    [ -r "${ETCD_SH}" ] || error "etcd script not found or not readable: ${ETCD_SH}"
    bash "${ETCD_SH}" clean || error "etcd data clean failed"
    bash "${ETCD_SH}" up || error "etcd init failed"
    success "etcd init completed"
}

# ===== deinit: 停 etcd + 删 unit（委托 etcd.sh down，保留数据） =====
# 与 init 互逆。仅停服务、删 unit，保留 /var/lib/agentos/etcd 数据，便于 restart。
# 彻底清数据由 init（自动 clean）或独立 ./etcd.sh clean 完成。
deploy_deinit() {
    echo ""
    info "Uninitializing etcd (stop + remove unit, data preserved)"
    [ -r "${ETCD_SH}" ] || error "etcd script not found or not readable: ${ETCD_SH}"
    bash "${ETCD_SH}" down || error "etcd deinit failed"
    success "etcd deinit completed"
}

deploy_down() {
    echo ""
    info "Starting full teardown (down)"
    info "Modules (reverse): $(reverse_modules)"
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

# ===== status: 一键查询各组件状态（只读探测，不启停服务） =====
# 输出格式：每个组件钩子输出若干行 `组件名|服务名|状态|详情`（机器可读），
# 由 _print_status_table 收集后统一格式化为表格输出。
# etcd 不在 MODULES 中，由 etcd.sh status 独立委托。
deploy_status() {
    echo ""
    info "Querying component status"

    local status_lines=()
    local overall_rc=0

    # 过滤辅助：只保留 `组件|服务|状态|详情` 格式的行，丢弃子脚本 info 日志
    _filter_status_lines() {
        while IFS= read -r line; do
            [ -n "${line}" ] || continue
            # 必须包含 3 个 | 分隔符（4 字段）
            local pipes
            pipes=$(echo "${line}" | tr -cd '|' | wc -c)
            [ "${pipes}" -ge 3 ] && echo "${line}"
        done
    }

    # 1. etcd（独立委托 etcd.sh status）
    if [ -r "${ETCD_SH}" ]; then
        local etcd_tmpfile
        etcd_tmpfile=$(mktemp)
        bash "${ETCD_SH}" status 2>/dev/null | _filter_status_lines > "${etcd_tmpfile}"
        local etcd_rc=${PIPESTATUS[0]}
        [ "${etcd_rc}" -ne 0 ] && overall_rc=1
        if [ -s "${etcd_tmpfile}" ]; then
            while IFS= read -r line; do
                [ -n "${line}" ] && status_lines+=("${line}")
            done < "${etcd_tmpfile}"
        fi
        rm -f "${etcd_tmpfile}"
    else
        status_lines+=("etcd|-|n/a|etcd.sh not found")
    fi

    # 2. 按 MODULES 正序遍历各模块 _status 钩子（独立遍历，不复用 run_hooks）
    #    缺失钩子的组件占位一行 "not supported"，不跳过
    local mod fn rc tmpfile
    for mod in "${MODULES[@]}"; do
        fn="${mod}_status"
        if ! declare -f "${fn}" >/dev/null 2>&1; then
            status_lines+=("${mod}|-|n/a|not supported")
            continue
        fi
        # 用临时文件避免 $() 命令替换中 PIPESTATUS 丢失返回码
        tmpfile=$(mktemp)
        "${fn}" 2>/dev/null | _filter_status_lines > "${tmpfile}"
        rc=${PIPESTATUS[0]}
        [ "${rc}" -ne 0 ] && overall_rc=1
        if [ -s "${tmpfile}" ]; then
            while IFS= read -r line; do
                [ -n "${line}" ] && status_lines+=("${line}")
            done < "${tmpfile}"
        fi
        rm -f "${tmpfile}"
    done

    _print_status_table "${status_lines[@]}"
    return ${overall_rc}
}

# ===== 状态表格化输出 + 汇总计数 =====
_print_status_table() {
    local -a lines=("$@")
    local running=0 stopped=0 failed=0 na=0 total=0
    local line comp svc state detail

    echo ""
    info "=== AgentOS Status ==="
    echo ""
    printf "%-16s %-42s %-10s %s\n" "Component" "Service" "State" "Detail"
    printf "%-16s %-42s %-10s %s\n" "------------" "----------------------------------------" "--------" "------------------------------"

    for line in "${lines[@]}"; do
        # 解析 `组件|服务|状态|详情` 格式
        IFS='|' read -r comp svc state detail <<< "${line}"
        [ -z "${comp:-}" ] && comp="-"
        [ -z "${svc:-}" ] && svc="-"
        [ -z "${state:-}" ] && state="unknown"
        [ -z "${detail:-}" ] && detail="-"

        total=$((total+1))
        case "${state}" in
            running)  running=$((running+1))  ;;
            stopped)  stopped=$((stopped+1))  ;;
            failed)   failed=$((failed+1))   ;;
            disabled) stopped=$((stopped+1)) ;;
            n/a|na)   na=$((na+1))           ;;
            *)        failed=$((failed+1))   ;;
        esac

        # 颜色编码：running 绿 / stopped 黄 / failed 红 / n/a 灰
        local colored_state
        case "${state}" in
            running)  colored_state="\033[32m${state}\033[0m"  ;;
            stopped|disabled) colored_state="\033[33m${state}\033[0m" ;;
            failed)   colored_state="\033[31m${state}\033[0m"  ;;
            n/a|na)   colored_state="\033[90m${state}\033[0m"   ;;
            *)        colored_state="\033[31m${state}\033[0m"  ;;
        esac

        printf "%-16s %-42s %-10b %s\n" "${comp}" "${svc}" "${colored_state}" "${detail}"
    done

    echo ""
    echo "=== Summary: ${running}/${total} running | ${stopped} stopped | ${failed} failed | ${na} N/A ==="
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

生命周期（三对互逆操作，嵌套如括号）:
  install  ↔  uninstall     装/卸 whl（最外层）
    init   ↔  deinit        bootstrap / 拆 etcd（中层，一次性）
      up   ↔  down          起/停应用服务（最内层，可反复）
  拆除顺序天然逆序: down → deinit → uninstall

Commands (Required):
  install     在本机安装全部组件的 whl 包（不启动服务）
  init        bootstrap etcd（委托 etcd.sh clean + up，非 etcd 节点自动跳过）
              自动清理历史 etcd 数据（默认 yes，对齐 yr start 语义），无需手动 clean
  up          按顺序部署全部应用组件（前置检查 etcd 可达，不可达则提示先 init）
  down        逆序停止全部应用组件（不动 etcd）
  deinit      停 etcd + 删 unit（委托 etcd.sh down，保留数据）
  uninstall   在本机卸载全部组件的 whl 包
  status      查询全部组件运行状态（只读探测，不启停服务；含 etcd + MODULES）
  restart     重启全部应用组件（先 down 再 up；不含 init/deinit）

Options:
  -h, --help      显示帮助信息

etcd 数据删除（独立操作，不并入 deinit；默认直接清理无交互确认）:
  ./etcd.sh clean   彻底删除 /var/lib/agentos/etcd 数据（对齐 yr start 语义）

Config:
  moosefs     配置文件: deploy/moosefs/moosefs.conf (端口/目录/副本数/systemd 开关等)
              默认部署分布式文件系统，通过 MOOSEFS_ENABLED=no 关闭
              master IP 从 deploy/config.yaml 的 master_nodes 第一个 IP 获取
              支持 openEuler (RPM) 和 Ubuntu (DEB)，自动检测包管理器
              systemd 可选: MOOSEFS_USE_SYSTEMD=auto/yes/no (默认 auto 自动检测)
              角色判断: 本机 IP 匹配 MOOSEFS_MASTER_HOST 为 master，否则为 agent
              生命周期: install(配置+unit生成) → up(enable --now) → down(stop) → uninstall(停止+清理)
              数据保留: MOOSEFS_PURGE_DATA=no(默认保留数据,重新install+up可恢复) / yes(彻底清理)
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
  - 本机需预装指定版本的 Python
  - jiuwenbox 部署前需确保 jiuwenswarm whl 包已安装（jiuwenbox-server 入口随 jiuwenswarm 安装）
  - jiuwenswarm/gateway 部署前需确保 openyuanrong 已在本机安装并启动
  - IMPORTANT: up 前需先执行 init 启动 etcd（up 会前置检查 etcd 可达性）

Examples:
  # ---- 单机完整生命周期 ----
  # 1. 本机安装全部 whl 包
  ./agentos.sh install

  # 2. bootstrap etcd（非 etcd 节点自动跳过）
  ./agentos.sh init

  # 3. 部署全部应用组件（自动前置检查 etcd 可达）
  ./agentos.sh up

  # 4. 停止应用组件（etcd 保持运行）
  ./agentos.sh down

  # 5. 拆除 etcd（保留数据）
  ./agentos.sh deinit

  # 6. 卸载全部 whl 包
  ./agentos.sh uninstall

  # ---- 多机部署（etcd 需全集群先就绪）----
  # 全节点 install → 全 etcd 节点 init（确认 quorum）→ 全节点 up

  # 重启应用组件（不含 etcd）
  ./agentos.sh restart

  # 查询全部组件状态（只读探测，不启停服务）
  ./agentos.sh status

  # 指定其他 whl 目录安装 yuanrong
  YR_PKG_BASE=/data/yr_whls ./agentos.sh install

  # 8. 自定义 agent SSH 直连密钥路径（默认 /root/.ssh/ 下，需用户自行生成）
  AGENTOS_SSH_KEY=/path/my_key \
  AGENTOS_SSH_BACKEND_PUBLIC_DIR=/path/my_pub \
  ./agentos.sh up

扩展模块:
  新增组件只需两步:
  1. 在 deploy/ 下新建 <module>/ 目录，放入 module.sh（实现 <module>_up/down/install/uninstall/status 钩子）
  2. 在本脚本顶部 MODULES 数组中添加模块名

注意:
  - up/restart 不安装 whl 包，请先执行 install
  - up 前需先执行 init：etcd 作为一次性 bootstrap 独立于 up/down（up 会前置检查可达性）
  - init 自动清理历史 etcd 数据（对齐 yr start 语义：每次 bootstrap 视为干净启动）
  - down 不停 etcd，etcd 作为持久基础设施；拆 etcd 用 deinit（保留数据），强制仅清数据用 ./etcd.sh clean
  - init/deinit 委托 deploy/etcd.sh，etcd 逻辑只在 etcd.sh 一处维护
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
        install)   deploy_install ;;
        init)      deploy_init ;;
        up)        deploy_up ;;
        down)      deploy_down ;;
        deinit)    deploy_deinit ;;
        uninstall) deploy_uninstall ;;
        status)    deploy_status ;;
        restart)   deploy_restart ;;
        *)         error "Unknown command: ${CMD}" ;;
    esac
}

main "$@"
