#!/usr/bin/env bash
# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# ST：跑通 build.sh 并校验产物存在
set -u

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST="${PROJECT_ROOT}/build/dist"

bash "${PROJECT_ROOT}/build/build.sh"

[ -f "${DIST}/AgentOS-Client.tgz" ] && echo "[PASS] AgentOS-Client.tgz" || { echo "[FAIL] AgentOS-Client.tgz"; exit 1; }
[ -f "${DIST}/AgentOS-Server.tgz" ] && echo "[PASS] AgentOS-Server.tgz" || { echo "[FAIL] AgentOS-Server.tgz"; exit 1; }

echo "ST done"
