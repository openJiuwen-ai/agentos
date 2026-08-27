#!/usr/bin/env bash
# ============================================================
# 模块: jiuwenswarm (函数 + gateway，whl 包已包含 gateway)
# 钩子函数: jiuwenswarm_up / jiuwenswarm_down / jiuwenswarm_install / jiuwenswarm_uninstall / jiuwenswarm_status
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

    # 工具沙箱镜像提示（install 不自动拉取镜像，up 也不检测，需用户手动 docker pull）
    _jiuwenswarm_warn_sandbox_image
}

# 提示用户手动拉取工具沙箱镜像
# install/up 均不自动下载镜像，用户需按 README 说明手动 docker pull
_jiuwenswarm_warn_sandbox_image() {
    local env_file="${JIUWENSWARM_DEPLOY_DIR}/.env.custom"
    local sandbox_type="" sandbox_enable="" sandbox_image=""

    # 从 .env.custom 读取工具沙箱配置
    if [ -f "${env_file}" ]; then
        sandbox_type=$(grep -E '^TOOL_SANDBOX_TYPE=' "${env_file}" 2>/dev/null | cut -d'"' -f2 || true)
        sandbox_enable=$(grep -E '^TOOL_SANDBOX_ENABLE=' "${env_file}" 2>/dev/null | cut -d'"' -f2 || true)
        sandbox_image=$(grep -E '^TOOL_SANDBOX_IMAGE=' "${env_file}" 2>/dev/null | cut -d'"' -f2 || true)
    fi

    # 仅当工具沙箱启用时提示
    if [ "${sandbox_enable}" = "true" ] && [ -n "${sandbox_image}" ]; then
        echo ""
        warning "Tool sandbox is enabled (TOOL_SANDBOX_ENABLE=true) but the sandbox image is NOT auto-pulled during install/up."
        warning "You MUST manually pull the image before using tool sandbox, otherwise jiuwen agent tool sandbox will not work:"
        echo ""
        echo "    docker pull ${sandbox_image}"
        echo ""
        warning "See deploy/README.md (Tool Sandbox Image section) for details."
        if [ -n "${sandbox_type}" ]; then
            info "Current TOOL_SANDBOX_TYPE: ${sandbox_type}"
        fi
    fi
}

# 停用并禁用 jiuwenswarm-gateway 和 jiuwenswarm-web 的 systemd 服务（本机），清理 unit 文件与 drop-in
# uninstall 是本机操作（与 install 对称），故仅处理本机 systemd 服务；
jiuwenswarm_disable_systemd() {
    command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ] || return 0
    local unit_file found=0
    # 枚举 gateway 和 web 两类 unit
    for unit_file in /etc/systemd/system/jiuwenswarm-gateway*.service /etc/systemd/system/jiuwenswarm-web*.service; do
        [ -f "${unit_file}" ] || continue
        found=1
        local svc_name
        svc_name=$(basename "${unit_file}" .service)
        info "Disabling systemd service ${svc_name}..."
        systemctl disable --now "${svc_name}" 2>/dev/null || true
        systemctl reset-failed "${svc_name}" 2>/dev/null || true
        rm -rf "${unit_file}" "/etc/systemd/system/${svc_name}.service.d"
    done

    systemctl daemon-reload 2>/dev/null || true
    if [ "${found}" -eq 1 ]; then
        success "jiuwenswarm systemd services disabled and cleaned up"
    else
        info "No jiuwenswarm systemd unit found, skipping"
    fi
}

jiuwenswarm_uninstall() {
    local local_host
    local_host=$(hostname -I 2>/dev/null | awk '{print $1}')
    [ -z "${local_host}" ] && local_host="127.0.0.1"

    # 先停用 systemd 服务，再卸载 pip 包，避免卸载后残留 unit 文件
    jiuwenswarm_disable_systemd

    if bash -c "python${YR_PYTHON_VERSION} -m pip uninstall -y jiuwenswarm openjiuwen 2>/dev/null"; then
        success "jiuwenswarm and openjiuwen uninstalled on ${local_host}"
    else
        warning "jiuwenswarm/openjiuwen not installed or failed to uninstall on ${local_host}"
    fi
}

# 只读探测本机 jiuwenswarm 运行状态
# 检测 jiuwenswarm-gateway 和 jiuwenswarm-web 两个服务
# 输出格式: jiuwenswarm|<service>|<state>|<detail>
jiuwenswarm_status() {
    local rc=0

    # systemd 模式：枚举 gateway 和 web 两类 unit
    if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
        local unit_file found=0
        for unit_file in /etc/systemd/system/jiuwenswarm-gateway*.service /etc/systemd/system/jiuwenswarm-web*.service; do
            [ -f "${unit_file}" ] || continue
            found=1
            local svc_name
            svc_name=$(basename "${unit_file}" .service)
            local state detail
            if systemctl is-active --quiet "${svc_name}" 2>/dev/null; then
                state="running"
                detail="active"
            elif systemctl is-failed --quiet "${svc_name}" 2>/dev/null; then
                state="failed"
                detail="failed"
                rc=1
            else
                state="stopped"
                detail="inactive"
            fi
            echo "jiuwenswarm|${svc_name}|${state}|${detail}"
        done
        if [ "${found}" -eq 1 ]; then
            return ${rc}
        fi
        # 无 unit 文件，落入进程模式
    fi

    # 进程模式：pgrep 检测 jiuwenswarm-gateway 和 jiuwenswarm-web
    _jwsw_pids_of() {
        local pat="$1"
        if command -v pgrep >/dev/null 2>&1; then
            pgrep -f "${pat}" 2>/dev/null || true
        else
            ps -ef 2>/dev/null | grep "${pat}" | grep -v grep | awk '{print $2}' || true
        fi
    }

    local gw_pids web_pids gw_alive=0 web_alive=0
    gw_pids=$(_jwsw_pids_of 'jiuwenswarm-gateway')
    [ -n "${gw_pids}" ] && gw_alive=1
    web_pids=$(_jwsw_pids_of 'jiuwenswarm-web')
    [ -n "${web_pids}" ] && web_alive=1

    # gateway 状态
    if [ "${gw_alive}" -eq 1 ]; then
        echo "jiuwenswarm|jiuwenswarm-gateway|running|active"
    else
        echo "jiuwenswarm|jiuwenswarm-gateway|stopped|no process"
    fi

    # web 状态
    if [ "${web_alive}" -eq 1 ]; then
        echo "jiuwenswarm|jiuwenswarm-web|running|active"
    else
        echo "jiuwenswarm|jiuwenswarm-web|stopped|no process"
    fi

    return ${rc}
}
