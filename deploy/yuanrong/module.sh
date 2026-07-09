#!/usr/bin/env bash
# ============================================================
# 模块: yuanrong (openyuanrong 集群)
# 钩子函数: yuanrong_up / yuanrong_down / yuanrong_install / yuanrong_uninstall
# ============================================================

YUANRONG_DEPLOY_DIR="${SCRIPT_DIR}/yuanrong"

# ===== 内部工具：调用 yuanrong_deploy.sh =====
_yuanrong_run() {
    local yr_script="${YUANRONG_DEPLOY_DIR}/yuanrong_deploy.sh"
    if [ ! -f "${yr_script}" ]; then
        error "yuanrong deploy script not found: ${yr_script}"
    fi
    bash "${yr_script}" "$@"
}

yuanrong_up() {
    _yuanrong_run up "$@"
}

yuanrong_down() {
    _yuanrong_run down "$@"
}

yuanrong_install() {
    # 默认从 agentos 根目录获取 whl 包，可通过 YR_PKG_BASE 环境变量覆盖
    if [ -z "${YR_PKG_BASE:-}" ]; then
        export YR_PKG_BASE="${AGENTOS_ROOT}"
        info "YR_PKG_BASE not set, using default: ${YR_PKG_BASE}"
    fi
    _yuanrong_run install "$@"
}

yuanrong_uninstall() {
    _yuanrong_run uninstall "$@"
}
