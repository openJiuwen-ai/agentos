#!/usr/bin/env bash
# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# ============================================================
# 模块: agent-runtime (Agent 分布式运行时，具体选型: openyuanrong 集群)
# 钩子函数: agent-runtime_up / agent-runtime_down / agent-runtime_status / agent-runtime_install / agent-runtime_uninstall
# ============================================================

AGENT_RUNTIME_DEPLOY_DIR="${SCRIPT_DIR}/agent-runtime"

# ===== 内部工具：调用 agent_runtime_deploy.sh =====
_agent_runtime_run() {
    local ar_script="${AGENT_RUNTIME_DEPLOY_DIR}/agent_runtime_deploy.sh"
    if [ ! -f "${ar_script}" ]; then
        error "agent-runtime deploy script not found: ${ar_script}"
    fi
    bash "${ar_script}" "$@"
}

agent-runtime_up() {
    _agent_runtime_run up "$@"
}

agent-runtime_down() {
    _agent_runtime_run down "$@"
}

agent-runtime_status() {
    _agent_runtime_run status "$@"
}

agent-runtime_install() {
    # 默认从 agentos 根目录获取 whl 包，可通过 YR_PKG_BASE 环境变量覆盖
    if [ -z "${YR_PKG_BASE:-}" ]; then
        export YR_PKG_BASE="${AGENTOS_ROOT}"
        info "YR_PKG_BASE not set, using default: ${YR_PKG_BASE}"
    fi
    _agent_runtime_run install "$@"
}

agent-runtime_uninstall() {
    _agent_runtime_run uninstall "$@"
}
