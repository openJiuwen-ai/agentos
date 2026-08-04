#!/usr/bin/env bash
# ============================================================
# 模块: jiuwenswarm (函数 + gateway，whl 包已包含 gateway)
# 钩子函数: jiuwenswarm_up / jiuwenswarm_down / jiuwenswarm_install / jiuwenswarm_uninstall
# ============================================================

# 构建时已将 jiuwenswarm submodule 中部署相关脚本文件拷贝到当前脚本执行目录中，故 deploy.sh 与 module.sh 同目录
JIUWENSWARM_DEPLOY_DIR="${SCRIPT_DIR}/jiuwenswarm"

# ===== up/down: 调用 deploy.sh =====
# deploy.sh 使用相对路径 source，需在其所在目录下执行
jiuwenswarm_up() {
    jiuwenswarm_run_deploy up "$@"
}

jiuwenswarm_down() {
    jiuwenswarm_run_deploy down "$@"
}

jiuwenswarm_run_deploy() {
    local sub_cmd="$1"
    shift
    local jw_script="${JIUWENSWARM_DEPLOY_DIR}/deploy.sh"
    if [ ! -f "${jw_script}" ]; then
        error "jiuwenswarm deploy script not found: ${jw_script}"
    fi

    local custom_env="${JIUWENSWARM_DEPLOY_DIR}/.env.custom"
    if [ ! -f "${custom_env}" ]; then
        warning "No .env.custom found at ${custom_env}, deploy.sh will use defaults"
    fi

    info "Deploying jiuwenswarm in ${JIUWENSWARM_DEPLOY_DIR}: ${sub_cmd} $*"
    (
        cd "${JIUWENSWARM_DEPLOY_DIR}"
        bash ./deploy.sh ${sub_cmd} "$@"
    )
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
        if bash -c "python${YR_PYTHON_VERSION} -m pip install '${jw_whl}[ssh]' --quiet"; then
            # 加固：pip show 确认包确实已注册到当前 Python 环境
            if bash -c "python${YR_PYTHON_VERSION} -m pip show jiuwenswarm >/dev/null 2>&1"; then
                success "jiuwenswarm installed on ${local_host}"
            else
                error "pip install returned success but 'pip show jiuwenswarm' failed on ${local_host} (wheel may be corrupted or installed to wrong env)"
            fi
        else
            error "Failed to install jiuwenswarm on ${local_host}"
        fi
    else
        warning "No jiuwenswarm whl found at ${AGENTOS_ROOT}/jiuwenswarm-*-py3-none-any.whl, skipping jiuwenswarm install"
        warning "Please place jiuwenswarm-<version>-py3-none-any.whl in ${AGENTOS_ROOT}/ before install"
    fi
}

# 停用并禁用 jiuwenswarm-gateway 的 systemd 服务（本机），清理 unit 文件与 drop-in
# uninstall 是本机操作（与 install 对称），故仅处理本机 systemd 服务；
jiuwenswarm_disable_systemd() {
    command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ] || return 0
    local unit_file found=0
    for unit_file in /etc/systemd/system/jiuwenswarm-gateway*.service; do
        [ -f "${unit_file}" ] || continue
        found=1
        local svc_name
        svc_name=$(basename "${unit_file}" .service)
        info "Disabling systemd service ${svc_name}..."
        systemctl disable --now "${svc_name}" 2>/dev/null || true
        rm -rf "${unit_file}" "/etc/systemd/system/${svc_name}.service.d"
    done

    systemctl daemon-reload 2>/dev/null || true
    if [ "${found}" -eq 1 ]; then
        success "jiuwenswarm-gateway systemd services disabled and cleaned up"
    else
        info "No jiuwenswarm-gateway systemd unit found, skipping"
    fi
}

jiuwenswarm_uninstall() {
    local local_host
    local_host=$(hostname -I 2>/dev/null | awk '{print $1}')
    [ -z "${local_host}" ] && local_host="127.0.0.1"

    # 先停用 systemd 服务，再卸载 pip 包，避免卸载后残留 unit 文件
    jiuwenswarm_disable_systemd

    if bash -c "python${YR_PYTHON_VERSION} -m pip uninstall -y jiuwenswarm 2>/dev/null"; then
        success "jiuwenswarm uninstalled on ${local_host}"
    else
        warning "jiuwenswarm not installed or failed to uninstall on ${local_host}"
    fi
}
