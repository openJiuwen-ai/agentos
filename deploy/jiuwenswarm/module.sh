#!/usr/bin/env bash
# ============================================================
# 模块: jiuwenswarm (函数 + gateway，whl 包已包含 gateway)
# 钩子函数: jiuwenswarm_up / jiuwenswarm_down / jiuwenswarm_install / jiuwenswarm_uninstall
# ============================================================

JIUWENSWARM_DEPLOY_DIR="${AGENTOS_ROOT}/jiuwenswarm/deploy/yuanrong"
JIUWENSWARM_CONFIG_DIR="${SCRIPT_DIR}/jiuwenswarm"

# ===== up/down: 调用 submodule 的 deploy.sh =====
# jiuwenswarm 的 deploy.sh 使用相对路径 source，必须在子模块的 deploy/yuanrong 目录下执行
# 配置文件统一放在 agentos/deploy/jiuwenswarm/.env.custom，执行前拷贝到子模块目录，执行后清理
jiuwenswarm_up() {
    jiuwenswarm_run_submodule_deploy up "$@"
}

jiuwenswarm_down() {
    jiuwenswarm_run_submodule_deploy down "$@"
}

jiuwenswarm_run_submodule_deploy() {
    local sub_cmd="$1"
    shift
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

    info "Deploying jiuwenswarm in ${JIUWENSWARM_DEPLOY_DIR}: ${sub_cmd} $*"
    (
        cd "${JIUWENSWARM_DEPLOY_DIR}"
        bash ./deploy.sh ${sub_cmd} "$@"
    )

    # 清理临时拷贝到子模块目录的配置文件，避免污染 submodule 工作区
    if [ "${copied}" = "true" ] && [ -f "${custom_env_dst}" ]; then
        rm -f "${custom_env_dst}"
        info "Cleaned up temporary config in submodule: ${custom_env_dst}"
    fi
}

# ===== install/uninstall: 本机 pip 操作 =====
# jiuwenswarm whl 包名格式: jiuwenswarm-<version>-py3-none-any.whl，已包含 gateway
jiuwenswarm_install() {
    local local_host
    local_host=$(hostname -I 2>/dev/null | awk '{print $1}')
    [ -z "${local_host}" ] && local_host="127.0.0.1"

    local found_whl
    found_whl=$(ls "${AGENTOS_ROOT}"/jiuwenswarm-*-py3-none-any.whl 2>/dev/null || true)
    if [ -n "${found_whl}" ]; then
        local jw_whl="${found_whl%%$'\n'*}"
        info "Found jiuwenswarm whl: ${jw_whl}"
        if bash -c "python${YR_PYTHON_VERSION} -m pip install '${jw_whl}' --quiet"; then
            success "jiuwenswarm installed on ${local_host}"
        else
            error "Failed to install jiuwenswarm on ${local_host}"
        fi
    else
        warning "No jiuwenswarm whl found at ${AGENTOS_ROOT}/jiuwenswarm-*-py3-none-any.whl, skipping jiuwenswarm install"
        warning "Please place jiuwenswarm-<version>-py3-none-any.whl in ${AGENTOS_ROOT}/ before install"
    fi
}

jiuwenswarm_uninstall() {
    local local_host
    local_host=$(hostname -I 2>/dev/null | awk '{print $1}')
    [ -z "${local_host}" ] && local_host="127.0.0.1"

    if bash -c "python${YR_PYTHON_VERSION} -m pip uninstall -y jiuwenswarm 2>/dev/null"; then
        success "jiuwenswarm uninstalled on ${local_host}"
    else
        warning "jiuwenswarm not installed or failed to uninstall on ${local_host}"
    fi
}
