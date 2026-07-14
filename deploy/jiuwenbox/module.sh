#!/usr/bin/env bash
# ============================================================
# 模块: jiuwenbox (沙箱服务，随 jiuwenswarm whl 包安装)
# 钩子函数: jiuwenbox_up / jiuwenbox_down
#
# 说明:
#   jiuwenbox 的 jiuwenbox-server 入口脚本随 jiuwenswarm whl 包安装，
#   因此不需要单独实现 install/uninstall 钩子。
#
#   default-policy.yaml 中的 __JIUWENSWARM_EXTENSIONS_DIR__ 占位符会在
#   start 时通过 pip show jiuwenswarm 动态替换为实际的 extensions 目录路径。
# ============================================================

JIUWENBOX_DEPLOY_DIR="${SCRIPT_DIR}/jiuwenbox"
JIUWENBOX_POLICY_TEMPLATE="${JIUWENBOX_DEPLOY_DIR}/default-policy.yaml"
JIUWENBOX_RUN_DIR="${AGENTOS_ROOT}/.run"

# ===== 内部工具：解析 jiuwenswarm extensions 目录 =====
# 优先使用 pip3.11，回退到 python3 -m pip
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

jiuwenbox_up() {
    local ext_dir
    ext_dir="$(_jiuwenbox_resolve_extensions_dir)"
    info "jiuwenswarm extensions dir: ${ext_dir}"

    local policy_file
    policy_file="$(_jiuwenbox_generate_policy "${ext_dir}")"
    info "generated jiuwenbox policy: ${policy_file}"

    _jiuwenbox_run --python "python${YR_PYTHON_VERSION}" start "${policy_file}" "$@"
}

jiuwenbox_down() {
    _jiuwenbox_run --python "python${YR_PYTHON_VERSION}" stop "$@"
}
