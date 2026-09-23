#!/usr/bin/env bash
# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# ============================================================
# 模块: jiuwenbox (沙箱服务，随 jiuwenswarm whl 包安装)
# 钩子函数: jiuwenbox_up / jiuwenbox_down / jiuwenbox_install / jiuwenbox_uninstall / jiuwenbox_status
#
# 说明:
#   薄封装，对齐 yuanrong/module.sh：up/down 逻辑在 jiuwenbox_deploy.sh。
#   jiuwenbox-server 入口随 jiuwenswarm whl 安装，无需单独 pip install。
# ============================================================

JIUWENBOX_DEPLOY_DIR="${SCRIPT_DIR}/jiuwenbox"

_jiuwenbox_run() {
    local jiuwenbox_script="${JIUWENBOX_DEPLOY_DIR}/jiuwenbox_deploy.sh"
    if [ ! -f "${jiuwenbox_script}" ]; then
        error "jiuwenbox deploy script not found: ${jiuwenbox_script}"
    fi
    bash "${jiuwenbox_script}" "$@"
}

jiuwenbox_up() {
    _jiuwenbox_run --python "python${YR_PYTHON_VERSION}" up "$@"
}

jiuwenbox_down() {
    _jiuwenbox_run --python "python${YR_PYTHON_VERSION}" down "$@"
}

jiuwenbox_install() {
    _jiuwenbox_run --python "python${YR_PYTHON_VERSION}" install "$@"
}

jiuwenbox_uninstall() {
    _jiuwenbox_run --python "python${YR_PYTHON_VERSION}" uninstall "$@"
}

jiuwenbox_status() {
    _jiuwenbox_run --python "python${YR_PYTHON_VERSION}" status "$@"
}
