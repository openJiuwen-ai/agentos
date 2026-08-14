#!/usr/bin/env bash
MOOSEFS_DEPLOY_DIR="${SCRIPT_DIR}/moosefs"

# 内部工具：调用 moosefs_deploy.sh
_moosefs_run() {
    local mfs_script="${MOOSEFS_DEPLOY_DIR}/moosefs_deploy.sh"
    if [ ! -f "${mfs_script}" ]; then
        error "moosefs deploy script not found: ${mfs_script}"
    fi
    bash "${mfs_script}" "$@"
}

moosefs_up() {
    _moosefs_run up "$@"
}

moosefs_down() {
    _moosefs_run down "$@"
}

moosefs_install() {
    # 从 agentos 根目录获取 RPM 包
    if [ -z "${AGENTOS_ROOT:-}" ]; then
        error "AGENTOS_ROOT not set"
    fi
    _moosefs_run install "$@"
}

moosefs_uninstall() {
    _moosefs_run uninstall "$@"
}
