#!/usr/bin/env bash
set -euo >/dev/null 2>&1

# ============================================================
# yuanrong 分布式部署独立脚本
# 完全自包含，不依赖任何其他文件
# 用法:
#   ./yuanrong_deploy.sh up --hosts 192.168.1.1,192.168.1.2
#   ./yuanrong_deploy.sh down --hosts 192.168.1.1,192.168.1.2
#   ./yuanrong_deploy.sh up    # 默认本机
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

YR_PYTHON_VERSION="${YR_PYTHON_VERSION:-3.11}"
YR_VERSION="${YR_VERSION:-0.9.0}"
CLUSTER_HOSTS=""
CMD=""

SSH_OPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"

# ===== 日志函数 =====
info() { echo -e "\033[36m=== $@ ===\033[0m"; }
success() { echo -e "\033[32m✅ $@\033[0m"; }
warning() { echo -e "\033[33m⚠️  $@\033[0m"; }
error() { echo -e "\033[31m❌ $@\033[0m"; exit 1; }

# ===== SSH 工具函数 =====
is_local_host() {
    local host="$1"
    if [ "${host}" = "127.0.0.1" ] || [ "${host}" = "localhost" ]; then
        return 0
    fi
    local local_ips
    local_ips=$(hostname -I 2>/dev/null || echo "")
    for ip in ${local_ips}; do
        if [ "${host}" = "${ip}" ]; then
            return 0
        fi
    done
    return 1
}

get_local_ip() {
    local local_ips
    local_ips=$(hostname -I 2>/dev/null || echo "")
    for ip in ${local_ips}; do
        if [ "${ip}" != "127.0.0.1" ] && [ "${ip}" != "localhost" ]; then
            echo "${ip}"
            return 0
        fi
    done
    echo "127.0.0.1"
}

exec_on_host() {
    local host="$1"
    shift
    if is_local_host "${host}"; then
        bash -c "$*"
    else
        ssh ${SSH_OPTS} root@${host} "$*"
    fi
}

copy_to_host() {
    local host="$1"
    local src="$2"
    local dst="$3"
    if is_local_host "${host}"; then
        local src_real
        src_real=$(realpath "${src}" 2>/dev/null || echo "${src}")
        local dst_real
        if [[ "${dst}" == */ ]]; then
            dst_real=$(realpath "${dst}" 2>/dev/null || echo "${dst}")
            dst_real="${dst_real}/$(basename "${src}")"
        else
            dst_real=$(realpath "${dst}" 2>/dev/null || echo "${dst}")
        fi
        if [ "${src_real}" = "${dst_real}" ]; then
            return 0
        fi
        cp -r "${src}" "${dst}"
    else
        scp ${SSH_OPTS} -r "${src}" "root@${host}:${dst}"
    fi
}

yr_check_ssh() {
    local host="$1"
    if is_local_host "${host}"; then
        return 0
    fi
    if ssh ${SSH_OPTS} root@${host} "echo ok" >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# ===== openyuanrong 安装/启动函数 =====
yr_detect_arch() {
    local host="$1"
    local arch
    arch=$(exec_on_host "${host}" "uname -m" 2>/dev/null | tr -d '\r')
    if [ "${arch}" = "x86_64" ]; then
        echo "x86_64"
    elif [ "${arch}" = "aarch64" ]; then
        echo "aarch64"
    else
        error "Unsupported architecture on ${host}: ${arch}"
    fi
}

yr_check_python() {
    local host="$1"
    local python_version="${YR_PYTHON_VERSION}"

    info "Checking Python ${python_version} on ${host}..."
    local py_check
    py_check=$(exec_on_host "${host}" "python${python_version} --version 2>&1" || echo "not_installed")

    if [[ "${py_check}" == *"not_installed"* ]] || [[ "${py_check}" == *"command not found"* ]] || [[ "${py_check}" == *"No module"* ]]; then
        error "Python ${python_version} is not installed on ${host}. Please install it manually before deploying."
    else
        success "Python ${python_version} already installed on ${host}: ${py_check}"
    fi
}

yr_ensure_pip() {
    local host="$1"
    local python_version="${YR_PYTHON_VERSION}"

    info "Ensuring pip on ${host}..."
    exec_on_host "${host}" "python${python_version} -m ensurepip 2>/dev/null || true"
}

yr_install_packages() {
    local host="$1"
    local python_version="${YR_PYTHON_VERSION}"
    local yr_version="${YR_VERSION}"
    local arch="$2"

    info "Installing openyuanrong packages on ${host}..."

    local default_base_url="https://openyuanrong.obs.cn-southwest-2.myhuaweicloud.com/release/${yr_version}/linux/${arch}"
    local pkg_base="${YR_PKG_BASE:-${default_base_url}}"
    # 去除末尾多余的斜杠，避免拼接出 // 路径
    while [[ "${pkg_base}" == */ ]]; do
        pkg_base="${pkg_base%/}"
    done
    local cp_tag="cp${python_version//./}"

    # 包名前缀（不含版本号），版本号通过 glob 通配匹配，不再要求显式指定 YR_VERSION
    local pkg_prefixes=(
        "openyuanrong"
        "openyuanrong_sdk"
        "openyuanrong_runtime"
        "openyuanrong_datasystem"
        "openyuanrong_functionsystem"
        "openyuanrong_faas"
    )
    # 每个包对应的 wheel 文件名 glob 模式
    local pkg_globs=(
        "openyuanrong-*-py3-none-manylinux_2_34_${arch}.whl"
        "openyuanrong_sdk-*-${cp_tag}-${cp_tag}-manylinux_2_34_${arch}.whl"
        "openyuanrong_runtime-*-${cp_tag}-${cp_tag}-manylinux_2_34_${arch}.whl"
        "openyuanrong_datasystem-*-${cp_tag}-${cp_tag}-manylinux_2_34_${arch}.whl"
        "openyuanrong_functionsystem-*-py3-none-manylinux_2_34_${arch}.whl"
        "openyuanrong_faas-*-${cp_tag}-${cp_tag}-manylinux_2_34_${arch}.whl"
    )

    # 判断 pkg_base 是远程URL还是本地路径
    local is_local_path=false
    if [[ "${pkg_base}" != http://* && "${pkg_base}" != https://* && "${pkg_base}" != ftp://* ]]; then
        is_local_path=true
        if [ ! -d "${pkg_base}" ]; then
            error "YR_PKG_BASE directory does not exist: ${pkg_base}"
        fi
        info "Using local package directory: ${pkg_base}"
    else
        info "Using remote package base URL: ${pkg_base}"
    fi

    # 本地路径: 用 glob 解析每个包的实际文件名（自动匹配任意版本号）
    # 远程URL : 仍用 YR_VERSION 拼接具体文件名
    local packages=()
    if [ "${is_local_path}" = "true" ]; then
        for idx in "${!pkg_globs[@]}"; do
            local glob="${pkg_globs[$idx]}"
            local prefix="${pkg_prefixes[$idx]}"
            # 取第一个匹配到的文件
            local matched
            matched=$(ls -1 "${pkg_base}"/${glob} 2>/dev/null | head -n 1)
            if [ -z "${matched}" ]; then
                error "No wheel matched pattern '${glob}' in ${pkg_base} (expected package: ${prefix})"
            fi
            # 仅保留文件名
            local fname
            fname=$(basename "${matched}")
            packages+=("${fname}")
            info "Matched wheel for ${prefix}: ${fname}"
        done
    else
        # 远程URL仍按 YR_VERSION 拼接固定文件名
        packages+=("openyuanrong-${yr_version}-py3-none-manylinux_2_34_${arch}.whl")
        packages+=("openyuanrong_sdk-${yr_version}-${cp_tag}-${cp_tag}-manylinux_2_34_${arch}.whl")
        packages+=("openyuanrong_runtime-${yr_version}-${cp_tag}-${cp_tag}-manylinux_2_34_${arch}.whl")
        packages+=("openyuanrong_datasystem-${yr_version}-${cp_tag}-${cp_tag}-manylinux_2_34_${arch}.whl")
        packages+=("openyuanrong_functionsystem-${yr_version}-py3-none-manylinux_2_34_${arch}.whl")
        packages+=("openyuanrong_faas-${yr_version}-${cp_tag}-${cp_tag}-manylinux_2_34_${arch}.whl")
    fi

    # 本地路径且目标主机非本机时,先把whl拷贝到目标主机
    local remote_pkg_dir=""
    if [ "${is_local_path}" = "true" ] && ! is_local_host "${host}"; then
        remote_pkg_dir="/tmp/yr_packages_${arch}"
        info "Copying whl packages to ${host}:${remote_pkg_dir}..."
        exec_on_host "${host}" "mkdir -p ${remote_pkg_dir}"
        for package in "${packages[@]}"; do
            local src_file="${pkg_base}/${package}"
            if [ ! -f "${src_file}" ]; then
                error "Package not found: ${src_file}"
            fi
            copy_to_host "${host}" "${src_file}" "${remote_pkg_dir}/"
        done
    fi

    for package in "${packages[@]}"; do
        local install_target
        if [ "${is_local_path}" = "true" ]; then
            if is_local_host "${host}"; then
                install_target="${pkg_base}/${package}"
                if [ ! -f "${install_target}" ]; then
                    error "Package not found: ${install_target}"
                fi
            else
                install_target="${remote_pkg_dir}/${package}"
            fi
        else
            install_target="${pkg_base}/${package}"
        fi
        info "Installing on ${host}: ${package}"
        if exec_on_host "${host}" "python${python_version} -m pip install '${install_target}' --quiet"; then
            # 加固：pip show 确认包确实已注册到当前 Python 环境
            # 从 wheel 文件名解析包名: 取第一个 '-' 之前的部分（openyuanrong_sdk -> openyuanrong.sdk 的分发名）
            local pkg_name="${package%%-*}"
            # pip 包名规范化: wheel 文件名用下划线，pip show 用连字符/点
            local pkg_show_name="${pkg_name//_/.}"
            if exec_on_host "${host}" "python${python_version} -m pip show '${pkg_show_name}' >/dev/null 2>&1"; then
                success "Installed on ${host}: ${package}"
            else
                error "pip install returned success but 'pip show ${pkg_show_name}' failed on ${host} (wheel may be corrupted or installed to wrong env)"
            fi
        else
            error "Failed to install on ${host}: ${package}"
        fi
    done
}

yr_uninstall_packages() {
    local host="$1"
    local python_version="${YR_PYTHON_VERSION}"

    local pkg_names=(
        "openyuanrong"
        "openyuanrong_sdk"
        "openyuanrong_runtime"
        "openyuanrong_datasystem"
        "openyuanrong_functionsystem"
        "openyuanrong_faas"
    )

    info "Uninstalling openyuanrong packages on ${host}..."
    for pkg in "${pkg_names[@]}"; do
        info "Uninstalling on ${host}: ${pkg}"
        if exec_on_host "${host}" "python${python_version} -m pip uninstall -y ${pkg} 2>/dev/null"; then
            success "Uninstalled on ${host}: ${pkg}"
        else
            warning "Package not installed or failed to uninstall on ${host}: ${pkg}"
        fi
    done
}

yr_verify_install() {
    local host="$1"

    info "Verifying yr command on ${host}..."
    if exec_on_host "${host}" "which yr" >/dev/null 2>&1; then
        success "yr command found on ${host}"
    else
        error "yr command not found on ${host}"
    fi
}

# ===== 进程清理与检测函数 =====
# 清理指定节点上残留的 yuanrong 进程:
#   1. 先 kill "yr start" 命令进程（避免其继续拉起服务）
#   2. 再 kill yr 运行时进程（命令行含 /yr/ 路径）
# 注: grep 模式使用字符类 (yr star[t] / /yr[/]) 避免匹配到当前清理命令自身
yr_cleanup_processes() {
    local host="$1"

    info "Cleaning up yuanrong processes on ${host}..."

    # 1. 清理 "yr start" 命令进程
    local start_pids
    start_pids=$(exec_on_host "${host}" "ps -ef | grep 'yr star[t]' | grep -v grep | awk '{print \$2}'" 2>/dev/null | tr -d '\r')
    if [ -n "${start_pids}" ]; then
        info "Found 'yr start' processes on ${host}, PIDs: ${start_pids}"
        for pid in ${start_pids}; do
            exec_on_host "${host}" "kill -9 ${pid}" 2>/dev/null && \
                info "Killed 'yr start' process ${pid} on ${host}" || \
                warning "Failed to kill 'yr start' process ${pid} on ${host}"
        done
    else
        info "No 'yr start' processes found on ${host}"
    fi

    # 2. 清理 yr 运行时进程（命令行含 /yr/ 路径）
    local yr_pids
    yr_pids=$(exec_on_host "${host}" "ps -ef | grep '/yr[/]' | grep -v grep | awk '{print \$2}'" 2>/dev/null | tr -d '\r')
    if [ -n "${yr_pids}" ]; then
        info "Found yr processes on ${host}, PIDs: ${yr_pids}"
        for pid in ${yr_pids}; do
            exec_on_host "${host}" "kill -9 ${pid}" 2>/dev/null && \
                info "Killed yr process ${pid} on ${host}" || \
                warning "Failed to kill yr process ${pid} on ${host}"
        done
    else
        info "No yr processes found on ${host}"
    fi

    return 0
}

# 在 yr start 前检测节点上是否已存在 yuanrong 集群/进程。
# 若已存在则直接报错退出，不自动清理，避免误杀原可用集群。
# 由用户决定是否执行 down/stop 后再重新 up。
yr_check_existing() {
    local host="$1"

    info "Checking for existing yuanrong processes on ${host}..."

    local start_pids yr_pids error_msg=""
    start_pids=$(exec_on_host "${host}" "ps -ef | grep 'yr star[t]' | grep -v grep | awk '{print \$2}'" 2>/dev/null | tr -d '\r')
    yr_pids=$(exec_on_host "${host}" "ps -ef | grep '/yr[/]' | grep -v grep | awk '{print \$2}'" 2>/dev/null | tr -d '\r')

    if [ -n "${start_pids}" ] || [ -n "${yr_pids}" ]; then
        [ -n "${start_pids}" ] && error_msg="${error_msg}'yr start' PIDs: ${start_pids}; "
        [ -n "${yr_pids}" ] && error_msg="${error_msg}yr PIDs: ${yr_pids}; "
        error "Existing yuanrong processes detected on ${host}: ${error_msg}Please run 'down' first to avoid launching duplicate clusters, then retry 'up'."
    else
        info "No existing yuanrong processes on ${host}"
    fi

    return 0
}

yr_start_master() {
    local master_host="$1"

    info "Starting openyuanrong master on ${master_host}..."

    local startup_log="/tmp/yr_startup_${master_host}.log"

    # 设置 TORCH_DEVICE_BACKEND_AUTOLOAD=0，避免环境 pytorch 问题导致函数实例拉不起来
    exec_on_host "${master_host}" "export TORCH_DEVICE_BACKEND_AUTOLOAD=0 && yr start --master \
        -s 'values.host_ip=\"${master_host}\"' \
        -s 'mode.master.frontend=true' \
        -s 'mode.master.function_scheduler=true' \
        -s 'mode.master.meta_service=true' \
        -s 'frontend.args.enableEvent=true'" 2>&1 | tee "${startup_log}"

    if grep -q "All components are healthy" "${startup_log}" 2>/dev/null || \
       grep -q "started" "${startup_log}" 2>/dev/null; then
        success "openyuanrong master started on ${master_host}"
    else
        error "Could not confirm master health on ${master_host}, no success marker found in ${startup_log}"
    fi

    local session_dir
    session_dir=$(exec_on_host "${master_host}" "readlink /tmp/yr_sessions/latest 2>/dev/null || echo ''" | tr -d '\r')
    info "Session dir on ${master_host}: ${session_dir}"
}

yr_start_agent() {
    local agent_host="$1"
    local master_host="$2"
    local master_address

    master_address=$(exec_on_host "${master_host}" "yr start --print_master_address 2>/dev/null || echo ''" | tr -d '\r')

    if [ -z "${master_address}" ]; then
        local session_dir
        session_dir=$(exec_on_host "${master_host}" "readlink /tmp/yr_sessions/latest 2>/dev/null || echo ''" | tr -d '\r')
        if [ -n "${session_dir}" ]; then
            master_address=$(exec_on_host "${master_host}" "grep -oP 'master_address=\K.*' ${session_dir}/config/yr_config.toml 2>/dev/null || echo ''" | tr -d '\r')
        fi
    fi

    if [ -z "${master_address}" ]; then
        master_address="${master_host}:22770"
        warning "Could not detect master address, using ${master_address}"
    fi

    info "Starting openyuanrong agent on ${agent_host}, master_address=${master_address}..."
    # 设置 TORCH_DEVICE_BACKEND_AUTOLOAD=0，避免环境 pytorch 问题导致函数实例拉不起来
    if exec_on_host "${agent_host}" "export TORCH_DEVICE_BACKEND_AUTOLOAD=0 && yr start -s 'values.host_ip=\"${agent_host}\"' --master_address=${master_address}" 2>&1; then
        success "openyuanrong agent started on ${agent_host}"
    else
        error "Failed to start openyuanrong agent on ${agent_host}"
    fi
}

yr_stop_all() {
    local hosts_str="${CLUSTER_HOSTS}"

    if [ -z "${hosts_str}" ]; then
        error "CLUSTER_HOSTS is not set. Cannot determine which hosts to stop."
    fi

    IFS=',' read -ra YR_HOST_LIST <<< "${hosts_str}"

    info "Stopping openyuanrong services..."

    for host in "${YR_HOST_LIST[@]}"; do
        info "Stopping yr on ${host} (force)..."
        exec_on_host "${host}" "yr stop --force" 2>/dev/null && \
            success "yr stopped on ${host}" || \
            warning "Failed to stop yr on ${host} (may not be running)"
        # 强制清理残留进程，避免多次 up/down 后进程堆积
        yr_cleanup_processes "${host}"
    done

    success "openyuanrong uninstall completed!"
}

# ===== 主流程 =====
deploy_yr_up() {
    local hosts_str="${CLUSTER_HOSTS}"
    local master_host
    # yr_up_phase:
    #   0 = 检测/校验阶段（check 失败不清理，避免误杀原可用集群）
    #   1 = 启动阶段（yr start 失败时清理本次拉起产生的残留进程）
    #   2 = 全部成功完成
    local yr_up_phase=0

    IFS=',' read -ra YR_HOST_LIST <<< "${hosts_str}"
    master_host="${YR_HOST_LIST[0]}"

    # 失败清理 trap:
    #   - 仅当已进入启动阶段 (phase>=1) 且未完成 (phase!=2) 时才清理本次拉起的残留进程
    #   - check 阶段 (phase=0) 失败（如发现已有集群）不清理，保护原可用集群
    trap '
        if [ "${yr_up_phase:-0}" = "1" ]; then
            warning "deploy_yr_up failed during startup phase, cleaning up residual yuanrong processes on all hosts..."
            for _h in "${YR_HOST_LIST[@]}"; do
                yr_cleanup_processes "${_h}"
            done
        fi
    ' EXIT

    info "Deploying openyuanrong in process mode"
    info "Master host: ${master_host}"
    info "Total hosts: ${#YR_HOST_LIST[@]}"
    info "Python version: ${YR_PYTHON_VERSION}"
    info "YR version: ${YR_VERSION}"

    info "Checking connectivity to all hosts..."
    for host in "${YR_HOST_LIST[@]}"; do
        if is_local_host "${host}"; then
            success "${host} is local host, skip SSH check"
        elif yr_check_ssh "${host}"; then
            success "SSH to ${host} OK"
        else
            error "SSH to ${host} failed! Please configure SSH key authentication first."
        fi
    done

    # up 不负责安装whl包，仅校验yr命令是否就绪（需先执行 install）
    for host in "${YR_HOST_LIST[@]}"; do
        yr_verify_install "${host}"
    done

    # 预检查：所有节点确认无残留 yuanrong 进程后才进入启动阶段。
    # 此处失败（发现已有集群）不触发清理，保护原可用集群。
    for host in "${YR_HOST_LIST[@]}"; do
        yr_check_existing "${host}"
    done

    # 进入启动阶段：此后任何失败都将触发清理
    yr_up_phase=1

    yr_start_master "${master_host}"

    if [ ${#YR_HOST_LIST[@]} -gt 1 ]; then
        info "Starting agent nodes..."
        for ((i=1; i<${#YR_HOST_LIST[@]}; i++)); do
            yr_start_agent "${YR_HOST_LIST[$i]}" "${master_host}"
        done
    fi

    yr_up_phase=2
    success "openyuanrong process-mode deployment completed!"
    echo ""
    echo "=========================================="
    success "Deployment Summary"
    echo "=========================================="
    echo "  Master: ${master_host}"
    if [ ${#YR_HOST_LIST[@]} -gt 1 ]; then
        echo "  Agents: ${YR_HOST_LIST[@]:1}"
    fi
    echo "=========================================="

    # 成功完成，清除失败清理 trap，避免影响后续命令
    trap - EXIT
}

deploy_yr_down() {
    yr_stop_all
}

deploy_yr_restart() {
    deploy_yr_down
    deploy_yr_up
}

deploy_yr_install() {
    local local_host
    local_host=$(get_local_ip)
    local arch

    info "Installing openyuanrong packages on local machine"
    info "Python version: ${YR_PYTHON_VERSION}"
    if [ -n "${YR_PKG_BASE:-}" ] && [[ "${YR_PKG_BASE}" != http://* && "${YR_PKG_BASE}" != https://* && "${YR_PKG_BASE}" != ftp://* ]]; then
        info "Package base: ${YR_PKG_BASE} (local directory, version auto-detected from whl filename)"
    else
        info "Package base: ${YR_PKG_BASE:-default OBS URL}"
        info "YR version: ${YR_VERSION} (used for remote URL path)"
    fi

    yr_check_python "${local_host}"
    yr_ensure_pip "${local_host}"

    arch=$(yr_detect_arch "${local_host}")
    info "Detected architecture: ${arch}"

    yr_install_packages "${local_host}" "${arch}"
    yr_verify_install "${local_host}"

    success "openyuanrong packages install completed!"
}

deploy_yr_uninstall() {
    local local_host
    local_host=$(get_local_ip)

    info "Uninstalling openyuanrong packages on local machine"
    info "Python version: ${YR_PYTHON_VERSION}"

    yr_uninstall_packages "${local_host}"

    success "openyuanrong packages uninstall completed!"
}

# ===== 参数解析 =====
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
                error "Invalid Args: ${args[$i]}"
                ;;
        esac
    done

    if [ -z "${CMD:-}" ]; then
        error "Command not specified! Use 'up', 'down', 'install' or 'uninstall'"
        exit 1
    fi

    # install/uninstall 仅在本机执行，不需要 CLUSTER_HOSTS
    if [[ "${CMD}" != "install" && "${CMD}" != "uninstall" ]]; then
        if [ -z "${CLUSTER_HOSTS:-}" ]; then
            CLUSTER_HOSTS=$(get_local_ip)
            warning "CLUSTER_HOSTS not specified, using local IP: ${CLUSTER_HOSTS}"
        fi
    fi

    info "Executing command: $*"
    info "CMD=${CMD}"
    if [[ "${CMD}" != "install" && "${CMD}" != "uninstall" ]]; then
        info "CLUSTER_HOSTS=${CLUSTER_HOSTS}"
    fi
}

print_help() {
    cat << EOF
Usage: ./$(basename "$0") [COMMAND] [OPTIONS]

独立部署 openyuanrong 分布式集群（进程模式）。
本脚本不依赖 deploy 目录下其他文件，可独立执行。

Commands (Required):
  up        启动 openyuanrong 集群（不安装whl包，需先在各主机执行 install）
  down      停止 openyuanrong 集群
  restart   重启 openyuanrong 集群（不安装whl包）
  install   仅在本机安装 openyuanrong whl 包（不启动服务，不需要 --hosts）
  uninstall 仅在本机卸载 openyuanrong whl 包（不需要 --hosts）

Options:
  --hosts HOSTS      目标主机IP列表，逗号分隔。第一个IP为master节点，其余为agent节点
                     仅 up/down/restart 命令需要，install/uninstall 忽略此参数
                     单机: --hosts 192.168.1.1
                     多机: --hosts 192.168.1.1,192.168.1.2,192.168.1.3
                     不指定时默认使用本机IP
  -h, --help         显示帮助信息

Environment Variables:
  YR_PYTHON_VERSION  Python版本（默认 3.11）
  YR_VERSION         openyuanrong release版本号（默认 0.9.0）。
                     仅当 YR_PKG_BASE 为远程URL时用于拼接下载路径，需与远端目录结构一致。
                     YR_PKG_BASE 为本地目录时无需指定，版本号会自动从 whl 文件名匹配。
  YR_PKG_BASE        whl包来源，可为远程URL基址或本地目录路径。
                     不指定时默认使用华为云OBS地址。
                     本地目录：目录下需包含与命名格式匹配的whl文件，远程主机会自动拷贝whl到目标机再安装。
                     本地目录示例: YR_PKG_BASE=/data/yr_whls
                     远程URL示例: YR_PKG_BASE=https://my-mirror/yr/0.9.0/linux/x86_64

Examples:
  # 典型流程：先在各主机安装whl包，再启动集群
  ./$(basename "$0") install                                          # 本机安装whl包（从默认OBS下载）
  YR_PKG_BASE=/data/yr_whls ./$(basename "$0") install               # 本机安装，使用本地whl目录（版本自动匹配）
  ./$(basename "$0") up --hosts 192.168.1.1                          # 单机启动集群
  ./$(basename "$0") up --hosts 192.168.1.1,192.168.1.2,192.168.1.3  # 多机启动集群
  ./$(basename "$0") up                                              # 默认本机启动集群
  ./$(basename "$0") down --hosts 192.168.1.1                        # 停止集群
  YR_VERSION=0.9.0 ./$(basename "$0") install                        # 从OBS安装指定版本
  ./$(basename "$0") uninstall                                        # 本机卸载whl包

注意:
  - 部署机器到所有目标主机需配置SSH免密登录
  - 目标主机需预装指定版本的Python
  - up/restart 不再安装whl包，请先在各目标主机执行 install（多机时每台主机都需安装）
EOF
    exit 0
}

main() {
    parse_args "$@"
    deploy_yr_${CMD}
}

main "$@"
