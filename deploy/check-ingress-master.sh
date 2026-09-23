#!/bin/bash
# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# agentos-check-ingress-master
# 由 agent-gateway install 时复制到 /usr/local/bin/agentos-check-ingress-master
# 供 systemd ExecStartPre 调用：检查本机是否持有 ingress_virtual_ip
# 非 master 时 exit 1 阻止服务启动
#
# 配置文件以 ~/.agentos/deploy/config.yaml 为准（install 持久化、用户可修改）
# 配置不存在或无 VIP 配置时允许启动（向后兼容单机/无 config 场景）
# stdout/stderr 由 systemd 自动记录到 journalctl

CONFIG_FILE="${HOME:-/root}/.agentos/deploy/config.yaml"

# 配置不存在时允许启动（向后兼容单机/无 config 场景）
if [ ! -f "${CONFIG_FILE}" ]; then
    echo "[agentos-check-ingress-master] config.yaml not found at ${CONFIG_FILE}, allowing start (single-node compat)"
    exit 0
fi

# 选择带 yaml 模块的 python（YR_* python 环境均内置 yaml）
PYTHON_BIN=""
for py in python3.11 python3 python; do
    if command -v "${py}" >/dev/null 2>&1 && "${py}" -c 'import yaml' >/dev/null 2>&1; then
        PYTHON_BIN="${py}"
        break
    fi
done

# 用 python+yaml 解析 cluster.ingress_virtual_ip（避免 grep+sed 正则误匹配注释行）
if [ -n "${PYTHON_BIN}" ]; then
    VIP=$("${PYTHON_BIN}" -c '
import sys, yaml
try:
    with open(sys.argv[1]) as f:
        cfg = yaml.safe_load(f)
    vip = (cfg or {}).get("cluster", {}).get("ingress_virtual_ip", "") or ""
    print(vip, end="")
except Exception:
    print("", end="")
' "${CONFIG_FILE}" 2>/dev/null)
else
    # 无 python/yaml 时回退 grep+sed（仅匹配行首为空白 + ingress_virtual_ip: 的配置行）
    VIP=$(grep '^[[:space:]]*ingress_virtual_ip:' "${CONFIG_FILE}" | head -1 \
        | sed 's/^[[:space:]]*ingress_virtual_ip:[[:space:]]*//' \
        | sed 's/#.*//' \
        | tr -d '"'"'"'' \
        | tr -d '[:space:]')
fi

# 无 VIP 配置时允许启动
if [ -z "${VIP}" ]; then
    echo "[agentos-check-ingress-master] ingress_virtual_ip not configured in ${CONFIG_FILE}, allowing start"
    exit 0
fi

# IPv4 格式校验（四段数字，点分隔），非法格式拒绝启动
if ! echo "${VIP}" | grep -qE '^([0-9]{1,3}\.){3}[0-9]{1,3}$'; then
    echo "[agentos-check-ingress-master] invalid IPv4 format: '${VIP}', refusing start" >&2
    exit 1
fi

# 检查本机是否持有该 IP
if hostname -I 2>/dev/null | tr ' ' '\n' | grep -qx "${VIP}"; then
    echo "[agentos-check-ingress-master] this node holds VIP ${VIP}, allowing start"
    exit 0
fi
if ip addr show 2>/dev/null | grep -qw "${VIP}"; then
    echo "[agentos-check-ingress-master] this node holds VIP ${VIP}, allowing start"
    exit 0
fi

echo "[agentos-check-ingress-master] this node does NOT hold VIP ${VIP}, refusing start" >&2
exit 1
