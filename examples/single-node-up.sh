#!/usr/bin/env bash
# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# ============================================================
# AgentOS 单机一键部署示例
#
# 演示 README Quick Start 的完整流程：
#   解包 -> 安装系统依赖 -> 配置 config.yaml -> 生成 agent SSH 密钥
#   -> agentos.sh install/init/up -> status
#
# 用法:
#   sudo ./single-node-up.sh --package /path/to/AgentOS-Server.tgz [选项]
#
# 选项:
#   --package PATH   必填，AgentOS-Server.tgz 路径
#   --ip IP          本机对外 IP（缺省自动探测；多网卡建议显式指定）
#   --skip-deps      跳过 install_deps.sh（依赖已预装时）
#   --workdir DIR    解压目录（默认 /tmp/agentos-example）
#
# 说明:
#   示例脚本仅供参考，请按实际环境修改。
#   config.yaml 的自动配置基于默认模板（三字段均为 127.0.0.1 时整体替换为目标 IP）。
# ============================================================
set -euo pipefail

usage() { grep '^#' "${BASH_SOURCE[0]}" | sed -n '3,22p'; exit 1; }

info()    { echo -e "\033[36m=== $@ ===\033[0m"; }
success() { echo -e "\033[32m✅ $@\033[0m"; }
error()   { echo -e "\033[31m❌ $@\033[0m" >&2; exit 1; }

PACKAGE=""
NODE_IP=""
SKIP_DEPS=0
WORKDIR="/tmp/agentos-example"

while [ $# -gt 0 ]; do
    case "$1" in
        --package)   PACKAGE="${2:?}"   ; shift 2 ;;
        --ip)        NODE_IP="${2:?}"   ; shift 2 ;;
        --skip-deps) SKIP_DEPS=1        ; shift   ;;
        --workdir)   WORKDIR="${2:?}"   ; shift 2 ;;
        -h|--help)   usage ;;
        *) echo "unknown option: $1" >&2; usage ;;
    esac
done

[ -n "${PACKAGE}" ] || usage
[ "$(id -u)" -eq 0 ] || error "please run as root"
[ -f "${PACKAGE}" ] || error "package not found: ${PACKAGE}"

# 1. 本机 IP：显式指定或自动探测，并校验为本机真实持有
if [ -z "${NODE_IP}" ]; then
    NODE_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
    [ -n "${NODE_IP}" ] || error "cannot detect local IP, use --ip to specify"
fi
ip addr show 2>/dev/null | grep -qw "${NODE_IP}" \
    || error "${NODE_IP} is not held by this host, use --ip to specify"
info "local IP: ${NODE_IP}"

# 2. 解包并定位 deploy/agentos.sh
info "extracting ${PACKAGE} -> ${WORKDIR}"
rm -rf "${WORKDIR}"
mkdir -p "${WORKDIR}"
tar -xzf "${PACKAGE}" -C "${WORKDIR}"
AGENTOS_SH="$(find "${WORKDIR}" -type f -name agentos.sh -path '*/deploy/*' | head -1)"
[ -n "${AGENTOS_SH}" ] || error "deploy/agentos.sh not found in package"
DEPLOY_DIR="$(cd "$(dirname "${AGENTOS_SH}")" && pwd)"

# 3. 系统依赖（可跳过）
if [ "${SKIP_DEPS}" -eq 0 ]; then
    info "installing system dependencies (deploy/install_deps.sh)"
    bash "${DEPLOY_DIR}/install_deps.sh"
else
    info "skipping install_deps.sh"
fi

# 4. 配置集群拓扑：默认模板整体替换 127.0.0.1 -> 本机 IP
CONFIG="${DEPLOY_DIR}/config.yaml"
if grep -q '127\.0\.0\.1' "${CONFIG}"; then
    info "configuring config.yaml with local IP ${NODE_IP}"
    sed -i "s/127\.0\.0\.1/${NODE_IP}/g" "${CONFIG}"
else
    info "config.yaml is not the default template, please edit it manually: ${CONFIG}"
fi

# 5. agent SSH 直连密钥（已存在则跳过）
if [ ! -f /root/.ssh/agent_key ]; then
    info "generating agent SSH key (/root/.ssh/agent_key)"
    ssh-keygen -t ed25519 -N '' -f /root/.ssh/agent_key
    mkdir -p /root/.ssh/agent_pub
    cp /root/.ssh/agent_key.pub /root/.ssh/agent_pub/authorized_keys
    chmod 644 /root/.ssh/agent_pub/authorized_keys
    chmod 755 /root/.ssh/agent_pub
else
    info "agent SSH key exists, skip"
fi

# 6. 安装 -> 初始化 -> 启动
info "agentos.sh install"
bash "${AGENTOS_SH}" install
info "agentos.sh init"
bash "${AGENTOS_SH}" init
info "agentos.sh up"
bash "${AGENTOS_SH}" up --ip "${NODE_IP}"

# 7. 状态确认
bash "${AGENTOS_SH}" status

success "AgentOS is up. Open http://${NODE_IP}:19000 in a browser to access the web frontend."
