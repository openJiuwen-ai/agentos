#!/usr/bin/env bash
# ============================================================
# 模块: jiuwenbox (沙箱服务，随 jiuwenswarm whl 包安装)
# 钩子函数: jiuwenbox_up / jiuwenbox_down
#
# 说明:
#   jiuwenbox 的 jiuwenbox-server 入口脚本随 jiuwenswarm whl 包安装。
#   控制机 up 前对所有 --hosts 做 status；若任一台已运行则执行
#   agentos.sh down 关闭全部服务并报错退出。
#
#   default-policy.yaml 中的 __JIUWENSWARM_EXTENSIONS_DIR__ 占位符会在
#   本机 local-up 时通过 pip show jiuwenswarm 动态替换。
#
#   多机: jiuwenbox_up/down 编排；每台走 _jiuwenbox_local_up/down。
#   远端: scp 本目录后执行 `bash module.sh local-up|local-down|local-status`。
# ============================================================

JIUWENBOX_DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JIUWENBOX_POLICY_TEMPLATE="${JIUWENBOX_DEPLOY_DIR}/default-policy.yaml"
# 与 jiuwenbox_deploy.sh 一致：运行态（含生成的 policy）落在 /tmp
JIUWENBOX_RUN_DIR="${JIUWENBOX_RUN_DIR:-/tmp/jiuwenbox}"

JIUWENBOX_SSH_OPTS="${JIUWENBOX_SSH_OPTS:--o StrictHostKeyChecking=accept-new -o ConnectTimeout=10}"
JIUWENBOX_REMOTE_STAGE="${JIUWENBOX_REMOTE_STAGE:-/tmp/agentos_jiuwenbox}"

# ===== 日志桩（远端独立执行时 agentos 未加载） =====
if ! declare -f info >/dev/null 2>&1; then
    info()    { echo -e "\033[36m=== $* ===\033[0m"; }
    success() { echo -e "\033[32m✅ $*\033[0m"; }
    warning() { echo -e "\033[33m⚠️  $*\033[0m"; }
    error()   { echo -e "\033[31m❌ $*\033[0m"; exit 1; }
fi

YR_PYTHON_VERSION="${YR_PYTHON_VERSION:-3.11}"

# ===== SSH 工具（对齐 yuanrong） =====
_jiuwenbox_is_local_host() {
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

_jiuwenbox_get_local_ip() {
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

_jiuwenbox_exec_on_host() {
    local host="$1"
    shift
    if _jiuwenbox_is_local_host "${host}"; then
        bash -c "$*"
    else
        ssh ${JIUWENBOX_SSH_OPTS} "root@${host}" "$*"
    fi
}

_jiuwenbox_copy_to_host() {
    local host="$1"
    local src="$2"
    local dst="$3"
    if _jiuwenbox_is_local_host "${host}"; then
        mkdir -p "$(dirname "${dst}")"
        if [ -d "${src}" ]; then
            mkdir -p "${dst}"
            cp -a "${src}/." "${dst}/"
        else
            mkdir -p "$(dirname "${dst}")"
            cp -a "${src}" "${dst}"
        fi
    else
        ssh ${JIUWENBOX_SSH_OPTS} "root@${host}" "mkdir -p $(dirname "${dst}")"
        if [ -d "${src}" ]; then
            ssh ${JIUWENBOX_SSH_OPTS} "root@${host}" "mkdir -p ${dst}"
            scp ${JIUWENBOX_SSH_OPTS} -r "${src}/." "root@${host}:${dst}/" >/dev/null 2>&1
        else
            scp ${JIUWENBOX_SSH_OPTS} -r "${src}" "root@${host}:${dst}" >/dev/null 2>&1
        fi
    fi
}

_jiuwenbox_check_ssh() {
    local host="$1"
    if _jiuwenbox_is_local_host "${host}"; then
        return 0
    fi
    if ssh ${JIUWENBOX_SSH_OPTS} "root@${host}" "echo ok" >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

# ===== 解析 --hosts =====
# 输出: 逗号分隔的 hosts；其余参数通过全局 _JIUWENBOX_EXTRA_ARGS 保留（一般为空）
_jiuwenbox_parse_hosts_args() {
    local hosts=""
    _JIUWENBOX_EXTRA_ARGS=()
    while [ $# -gt 0 ]; do
        case "$1" in
            --hosts)
                if [ $# -lt 2 ]; then
                    error "--hosts requires a comma-separated host list"
                fi
                hosts="$2"
                shift 2
                ;;
            --hosts=*)
                hosts="${1#--hosts=}"
                shift
                ;;
            *)
                _JIUWENBOX_EXTRA_ARGS+=("$1")
                shift
                ;;
        esac
    done
    if [ -z "${hosts}" ]; then
        if [ -n "${CLUSTER_HOSTS:-}" ]; then
            hosts="${CLUSTER_HOSTS}"
        else
            hosts="$(_jiuwenbox_get_local_ip)"
            # 必须写 stderr，否则会被 $(...) 捕获进 hosts 字符串
            warning "CLUSTER_HOSTS not specified, using local IP: ${hosts}" >&2
        fi
    fi
    echo "${hosts}"
}

# ===== 内部工具：解析 jiuwenswarm extensions 目录 =====
_jiuwenbox_resolve_extensions_dir() {
    local pip_cmd=""
    if command -v pip3.11 >/dev/null 2>&1; then
        pip_cmd="pip3.11"
    elif command -v "pip${YR_PYTHON_VERSION}" >/dev/null 2>&1; then
        pip_cmd="pip${YR_PYTHON_VERSION}"
    else
        pip_cmd="python${YR_PYTHON_VERSION} -m pip"
    fi

    local location=""
    location="$(${pip_cmd} show jiuwenswarm 2>/dev/null | awk '/^Location:/{print $2}')" || true
    if [ -z "${location}" ]; then
        error "Cannot resolve jiuwenswarm package location via '${pip_cmd} show jiuwenswarm'. Is jiuwenswarm installed?"
    fi

    local ext_dir="${location}/jiuwenswarm/extensions"
    if [ ! -d "${ext_dir}" ]; then
        warning "extensions directory not found: ${ext_dir} (binding anyway)"
    fi
    echo "${ext_dir}"
}

# ===== 内部工具：生成 policy 文件（替换占位符） =====
_jiuwenbox_generate_policy() {
    local ext_dir="$1"
    local out_dir="${JIUWENBOX_RUN_DIR}"
    mkdir -p "${out_dir}"

    local out_file="${out_dir}/jiuwenbox-policy.yaml"
    if [ ! -f "${JIUWENBOX_POLICY_TEMPLATE}" ]; then
        error "policy template not found: ${JIUWENBOX_POLICY_TEMPLATE}"
    fi

    sed "s|__JIUWENSWARM_EXTENSIONS_DIR__|${ext_dir}|g" "${JIUWENBOX_POLICY_TEMPLATE}" >"${out_file}"
    echo "${out_file}"
}

# ===== 内部工具：调用 jiuwenbox_deploy.sh =====
_jiuwenbox_run() {
    local jb_script="${JIUWENBOX_DEPLOY_DIR}/jiuwenbox_deploy.sh"
    if [ ! -f "${jb_script}" ]; then
        error "jiuwenbox deploy script not found: ${jb_script}"
    fi
    bash "${jb_script}" "$@"
}

# ===== 本机核心（不带 --hosts，不回调 agentos） =====
_jiuwenbox_local_up() {
    local ext_dir
    ext_dir="$(_jiuwenbox_resolve_extensions_dir)"
    info "jiuwenswarm extensions dir: ${ext_dir}"

    local policy_file
    policy_file="$(_jiuwenbox_generate_policy "${ext_dir}")"
    info "generated jiuwenbox policy: ${policy_file}"

    _jiuwenbox_run --python "python${YR_PYTHON_VERSION}" start "${policy_file}"
}

_jiuwenbox_local_down() {
    _jiuwenbox_run --python "python${YR_PYTHON_VERSION}" stop
}

_jiuwenbox_local_status() {
    _jiuwenbox_run status
}

# ===== 远端：同步脚本并调用 local-* =====
_jiuwenbox_sync_remote_stage() {
    local host="$1"
    local remote_dir="${JIUWENBOX_REMOTE_STAGE}/jiuwenbox"
    info "Syncing jiuwenbox scripts to ${host}:${remote_dir}"
    _jiuwenbox_exec_on_host "${host}" "mkdir -p '${remote_dir}'"
    scp ${JIUWENBOX_SSH_OPTS} \
        "${JIUWENBOX_DEPLOY_DIR}/module.sh" \
        "${JIUWENBOX_DEPLOY_DIR}/jiuwenbox_deploy.sh" \
        "${JIUWENBOX_DEPLOY_DIR}/default-policy.yaml" \
        "root@${host}:${remote_dir}/" >/dev/null 2>&1
}

_jiuwenbox_remote_local_cmd() {
    local host="$1"
    local cmd="$2"  # local-up | local-down | local-status
    local remote_module="${JIUWENBOX_REMOTE_STAGE}/jiuwenbox/module.sh"
    _jiuwenbox_sync_remote_stage "${host}"
    _jiuwenbox_exec_on_host "${host}" \
        "YR_PYTHON_VERSION='${YR_PYTHON_VERSION}' JIUWENBOX_RUN_DIR='${JIUWENBOX_RUN_DIR}' bash '${remote_module}' '${cmd}'"
}

_jiuwenbox_on_host() {
    local host="$1"
    local cmd="$2"
    if _jiuwenbox_is_local_host "${host}"; then
        case "${cmd}" in
            local-up)     _jiuwenbox_local_up ;;
            local-down)   _jiuwenbox_local_down ;;
            local-status) _jiuwenbox_local_status ;;
            *) error "unknown local cmd: ${cmd}" ;;
        esac
    else
        _jiuwenbox_remote_local_cmd "${host}" "${cmd}"
    fi
}

_jiuwenbox_check_connectivity() {
    local hosts_str="$1"
    local host
    IFS=',' read -ra _jb_hosts <<< "${hosts_str}"
    info "Checking connectivity to all jiuwenbox hosts..."
    for host in "${_jb_hosts[@]}"; do
        host="$(echo "${host}" | tr -d '[:space:]')"
        [ -z "${host}" ] && continue
        if _jiuwenbox_is_local_host "${host}"; then
            success "${host} is local host, skip SSH check"
        elif _jiuwenbox_check_ssh "${host}"; then
            success "SSH to ${host} OK"
        else
            error "SSH to ${host} failed! Please configure SSH key authentication first."
        fi
    done
}

# 任一台在跑则返回 0，并打印各 host 状态
_jiuwenbox_any_running() {
    local hosts_str="$1"
    local host
    local any=1
    local status_out=""
    IFS=',' read -ra _jb_hosts <<< "${hosts_str}"
    for host in "${_jb_hosts[@]}"; do
        host="$(echo "${host}" | tr -d '[:space:]')"
        [ -z "${host}" ] && continue
        if status_out="$(_jiuwenbox_on_host "${host}" local-status 2>&1)"; then
            warning "[${host}] ${status_out}"
            any=0
        else
            info "[${host}] jiuwenbox is not running"
        fi
    done
    return ${any}
}

# ===== 编排入口（agentos 钩子） =====
jiuwenbox_up() {
    local hosts_str
    hosts_str="$(_jiuwenbox_parse_hosts_args "$@")"
    local host

    info "jiuwenbox up hosts: ${hosts_str}"
    _jiuwenbox_check_connectivity "${hosts_str}"

    if _jiuwenbox_any_running "${hosts_str}"; then
        warning "running agentos.sh down to stop all services"
        local agentos_script="${SCRIPT_DIR:-$(cd "${JIUWENBOX_DEPLOY_DIR}/.." && pwd)}/agentos.sh"
        if [ -f "${agentos_script}" ]; then
            bash "${agentos_script}" down --hosts "${hosts_str}" >/dev/null 2>&1 || true
        else
            warning "agentos.sh not found at ${agentos_script}; stopping jiuwenbox on all hosts only"
            IFS=',' read -ra _jb_hosts <<< "${hosts_str}"
            for host in "${_jb_hosts[@]}"; do
                host="$(echo "${host}" | tr -d '[:space:]')"
                [ -z "${host}" ] && continue
                _jiuwenbox_on_host "${host}" local-down || true
            done
        fi
        error "jiuwenbox is already running on at least one host; refused to start. All services have been stopped via agentos.sh down."
    fi

    IFS=',' read -ra _jb_hosts <<< "${hosts_str}"
    for host in "${_jb_hosts[@]}"; do
        host="$(echo "${host}" | tr -d '[:space:]')"
        [ -z "${host}" ] && continue
        info "Starting jiuwenbox on ${host}..."
        _jiuwenbox_on_host "${host}" local-up
        success "jiuwenbox started on ${host}"
    done
}

jiuwenbox_down() {
    local hosts_str
    hosts_str="$(_jiuwenbox_parse_hosts_args "$@")"
    local host

    info "jiuwenbox down hosts: ${hosts_str}"
    _jiuwenbox_check_connectivity "${hosts_str}"

    IFS=',' read -ra _jb_hosts <<< "${hosts_str}"
    for host in "${_jb_hosts[@]}"; do
        host="$(echo "${host}" | tr -d '[:space:]')"
        [ -z "${host}" ] && continue
        info "Stopping jiuwenbox on ${host}..."
        _jiuwenbox_on_host "${host}" local-down || warning "Failed to stop jiuwenbox on ${host} (may not be running)"
        success "jiuwenbox stopped on ${host}"
    done
}

# ===== 远端独立入口：bash module.sh local-up|local-down|local-status =====
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    case "${1:-}" in
        local-up)
            _jiuwenbox_local_up
            ;;
        local-down)
            _jiuwenbox_local_down
            ;;
        local-status)
            _jiuwenbox_local_status
            ;;
        *)
            echo "Usage: $0 {local-up|local-down|local-status}" >&2
            exit 1
            ;;
    esac
fi
