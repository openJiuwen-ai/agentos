#!/usr/bin/env bash
# ============================================================
# 模块: conch (Conch + StratoVirt + erofs-utils RPM)
# 钩子函数: conch_up / conch_down / conch_install / conch_uninstall / conch_status
# ============================================================

CONCH_DEPLOY_DIR="${SCRIPT_DIR}/conch"

_conch_run() {
    local conch_script="${CONCH_DEPLOY_DIR}/conch_deploy.sh"
    if [ ! -f "${conch_script}" ]; then
        error "conch deploy script not found: ${conch_script}"
    fi
    bash "${conch_script}" "$@"
}

conch_up() {
    _conch_run up "$@"
}

conch_down() {
    _conch_run down "$@"
}

conch_install() {
    _conch_run install "$@"
}

conch_uninstall() {
    _conch_run uninstall "$@"
}

conch_status() {
    _conch_run status "$@"
}
