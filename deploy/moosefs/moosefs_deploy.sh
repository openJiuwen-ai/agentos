#!/usr/bin/env bash
# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
set -euo >/dev/null 2>&1

# ============================================================
# MooseFS 分布式存储部署独立脚本
# 完全自包含，不依赖任何其他文件
# 用法:
#   ./moosefs_deploy.sh install
#   ./moosefs_deploy.sh up --ip 192.168.1.1
#   ./moosefs_deploy.sh down --ip 192.168.1.1
#   ./moosefs_deploy.sh uninstall
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CMD=""
BIND_IP="${BIND_IP:-}"

# ===== 日志函数 =====
info()    { echo -e "\033[36m=== $@ ===\033[0m"; }
success() { echo -e "\033[32m✅ $@\033[0m"; }
warning() { echo -e "\033[33m⚠️  $@\033[0m"; }
error()   { echo -e "\033[31m❌ $@\033[0m"; exit 1; }

# ===== 本机 IP 探测与工具函数 =====
# 取本机所有 IPv4 地址。hostname -I 不可用时回退到 ip addr、/etc/hosts、ifconfig。
_get_local_ips() {
    local ips
    ips=$(hostname -I 2>/dev/null || true)
    if [ -n "${ips}" ]; then
        echo "${ips}"
        return
    fi
    # 回退 1：ip addr show
    if command -v ip >/dev/null 2>&1; then
        ip -4 addr show 2>/dev/null | grep -oE "inet [0-9.]+" | awk '{print $2}' | grep -v "^127\."
        return
    fi
    # 回退 2：/etc/hosts 里本机 hostname 对应的 IP
    local hname
    hname=$(cat /etc/hostname 2>/dev/null || true)
    if [ -n "${hname}" ]; then
        grep -E "^[0-9.]+[[:space:]]+.*${hname}" /etc/hosts 2>/dev/null | awk '{print $1}'
    fi
    # 回退 3：ifconfig 的 inet 地址
    if command -v ifconfig >/dev/null 2>&1; then
        ifconfig 2>/dev/null | grep -oE "inet [0-9.]+" | awk '{print $2}' | grep -v "^127\."
    fi
}

is_local_host() {
    local host="$1"
    if [ "${host}" = "127.0.0.1" ] || [ "${host}" = "localhost" ]; then
        return 0
    fi
    # --ip 指定时只认指定 IP，避免多网卡下误判
    if [ -n "${BIND_IP}" ]; then
        [ "${host}" = "${BIND_IP}" ] && return 0 || return 1
    fi
    local local_ips
    local_ips=$(_get_local_ips)
    for ip in ${local_ips}; do
        if [ "${host}" = "${ip}" ]; then
            return 0
        fi
    done
    return 1
}

get_local_ip() {
    # --ip 指定时直接返回，跳过自动探测
    if [ -n "${BIND_IP}" ]; then
        echo "${BIND_IP}"
        return 0
    fi
    local local_ips
    local_ips=$(_get_local_ips)
    for ip in ${local_ips}; do
        if [ "${ip}" != "127.0.0.1" ] && [ "${ip}" != "localhost" ]; then
            echo "${ip}"
            return 0
        fi
    done
    echo "127.0.0.1"
}

# ===== 本机执行封装（不再 SSH 到远端）=====
exec_on_host() {
    local host="$1"
    shift
    bash -c "$*"
}

copy_to_host() {
    local host="$1"
    local src="$2"
    local dst="$3"
    local src_real
    src_real=$(realpath "${src}" 2>/dev/null || echo "${src}")
    local dst_real
    if [[ "${dst}" == */ ]]; then
        dst_real=$(realpath "${dst}" 2>/dev/null || echo "${dst}")
        dst_real="${dst_real}/$(basename "${src}")"
    else
        dst_real=$(realpath "${dst}" 2>/dev/null || echo "${dst}")
    fi
    if [ "${src_real}" = "${dst_real}" ]; then
        return 0
    fi
    cp -r "${src}" "${dst}"
}

# ===== 读取 deploy/config.yaml 获取 master IP =====
_mfs_load_config_yaml() {
    local config_yaml="${SCRIPT_DIR}/../config.yaml"
    if [ ! -f "${config_yaml}" ]; then
        return
    fi

    # 从 config.yaml 中提取 master_nodes 列表，取第一个 IP
    # 只支持简单 YAML 解析：匹配 "master_nodes:" 后的 "- IP" 行
    local in_master_nodes=false
    local first_master_ip=""
    while IFS= read -r line; do
        # 去除前后空白
        line="${line#"${line%%[![:space:]]*}"}"
        # 检测进入 master_nodes 段
        if [[ "${line}" =~ ^master_nodes: ]]; then
            in_master_nodes=true
            continue
        fi
        # 检测离开 master_nodes 段（新的顶层 key）
        if [ "${in_master_nodes}" = "true" ]; then
            if [[ "${line}" =~ ^[a-zA-Z_] ]]; then
                in_master_nodes=false
                continue
            fi
            # 提取 "- IP" 行中的 IP
            if [[ "${line}" =~ ^-[[:space:]]*\"([0-9.]+)\" ]]; then
                first_master_ip="${BASH_REMATCH[1]}"
                break
            elif [[ "${line}" =~ ^-[[:space:]]*([0-9.]+) ]]; then
                first_master_ip="${BASH_REMATCH[1]}"
                break
            fi
        fi
    done < "${config_yaml}"

    if [ -n "${first_master_ip}" ]; then
        MOOSEFS_MASTER_HOST="${first_master_ip}"
    fi
}

# ===== 配置加载函数 =====
_mfs_load_config() {
    # 保存环境变量（优先级最高，不被配置文件覆盖）
    local _env_master_host="${MOOSEFS_MASTER_HOST:-}"
    local _env_enabled="${MOOSEFS_ENABLED:-}"
    local _env_use_systemd="${MOOSEFS_USE_SYSTEMD:-}"
    local _env_master_port="${MFS_MASTER_PORT:-}"
    local _env_chunk_port="${MFS_CHUNK_PORT:-}"
    local _env_client_port="${MFS_CLIENT_PORT:-}"
    local _env_chunk_dir="${MFS_CHUNK_DIR:-}"
    local _env_mount_point="${MFS_MOUNT_POINT:-}"
    local _env_goal="${MFS_GOAL:-}"
    local _env_purge_data="${MOOSEFS_PURGE_DATA:-}"

    # 1. 读取 deploy/config.yaml 获取 master IP（最低优先级）
    _mfs_load_config_yaml

    # 保存 config.yaml 读到的 master host（防止被 moosefs.conf 的空值覆盖）
    local _yaml_master_host="${MOOSEFS_MASTER_HOST:-}"

    # 2. 读取 moosefs.conf
    local conf_file="${SCRIPT_DIR}/moosefs.conf"
    if [ -f "${conf_file}" ]; then
        source "${conf_file}"
    fi

    # moosefs.conf 中 MOOSEFS_MASTER_HOST="" 不应覆盖 config.yaml 读到的值
    [ -z "${MOOSEFS_MASTER_HOST:-}" ] && [ -n "${_yaml_master_host}" ] && MOOSEFS_MASTER_HOST="${_yaml_master_host}"

    # 3. 环境变量优先级最高：如果环境变量已设置则恢复
    [ -n "${_env_master_host}" ]  && MOOSEFS_MASTER_HOST="${_env_master_host}"
    [ -n "${_env_enabled}" ]      && MOOSEFS_ENABLED="${_env_enabled}"
    [ -n "${_env_use_systemd}" ]  && MOOSEFS_USE_SYSTEMD="${_env_use_systemd}"
    [ -n "${_env_master_port}" ]  && MFS_MASTER_PORT="${_env_master_port}"
    [ -n "${_env_chunk_port}" ]   && MFS_CHUNK_PORT="${_env_chunk_port}"
    [ -n "${_env_client_port}" ]  && MFS_CLIENT_PORT="${_env_client_port}"
    [ -n "${_env_chunk_dir}" ]    && MFS_CHUNK_DIR="${_env_chunk_dir}"
    [ -n "${_env_mount_point}" ]  && MFS_MOUNT_POINT="${_env_mount_point}"
    [ -n "${_env_goal}" ]         && MFS_GOAL="${_env_goal}"
    [ -n "${_env_purge_data}" ]   && MOOSEFS_PURGE_DATA="${_env_purge_data}"

    # 设置默认值
    : "${MOOSEFS_MASTER_HOST:=""}"
    : "${MOOSEFS_ENABLED:="auto"}"
    : "${MOOSEFS_USE_SYSTEMD:="auto"}"
    : "${MFS_MASTER_PORT:="9420"}"
    : "${MFS_CHUNK_PORT:="9422"}"
    : "${MFS_CLIENT_PORT:="9421"}"
    : "${MFS_CHUNK_DIR:="/data/mfschunks"}"
    : "${MFS_MOUNT_POINT:="/home/agentos/users"}"
    : "${MFS_GOAL:="2"}"
    : "${MOOSEFS_PURGE_DATA:="no"}"
}

# ===== 二进制路径查找 =====
_mfs_bin() {
    local cmd="$1"
    local p
    for p in /usr/sbin /usr/bin /usr/local/sbin /usr/local/bin; do
        if [ -x "${p}/${cmd}" ]; then
            echo "${p}/${cmd}"
            return 0
        fi
    done
    # 回退：找不到就用命令名本身，让 PATH 去解析
    echo "${cmd}"
}

MFS_BIN_MASTER=$(_mfs_bin mfsmaster)
MFS_BIN_CHUNKSERVER=$(_mfs_bin mfschunkserver)
MFS_BIN_MOUNT=$(_mfs_bin mfsmount)
MFS_BIN_SETGOAL=$(_mfs_bin mfssetgoal)

# ===== systemd 三态检测函数 =====
_mfs_should_use_systemd() {
    case "${MOOSEFS_USE_SYSTEMD}" in
        yes)
            if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
                return 0
            else
                error "MOOSEFS_USE_SYSTEMD=yes but systemd is not available on this system"
            fi
            ;;
        no)
            return 1
            ;;
        auto)
            if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
                return 0
            else
                return 1
            fi
            ;;
        *)
            error "Invalid MOOSEFS_USE_SYSTEMD value: ${MOOSEFS_USE_SYSTEMD} (expected: auto/yes/no)"
            ;;
    esac
}

# ===== 角色判断函数 =====
# master 判定：MOOSEFS_MASTER_HOST（从 config.yaml 解析）等于本机 IP 则是 master
_mfs_is_master() {
    local local_ip
    local_ip=$(get_local_ip)

    if [ -z "${MOOSEFS_MASTER_HOST:-}" ]; then
        warning "MOOSEFS_MASTER_HOST not set, cannot determine role"
        return 1
    fi
    if [ "${local_ip}" = "${MOOSEFS_MASTER_HOST}" ] || is_local_host "${MOOSEFS_MASTER_HOST}"; then
        return 0
    fi

    return 1
}

# ===== MOOSEFS_MASTER_HOST 解析 =====
_mfs_resolve_master_host() {
    echo "${MOOSEFS_MASTER_HOST:-}"
}

# ===== 模式选择与单机跳过 =====
_mfs_should_skip() {
    case "${MOOSEFS_ENABLED}" in
        yes)
            return 1
            ;;
        no)
            return 0
            ;;
        auto)
            # 默认部署，仅当显式设为 no 时才跳过
            return 1
            ;;
        *)
            error "Invalid MOOSEFS_ENABLED value: ${MOOSEFS_ENABLED} (expected: auto/yes/no)"
            ;;
    esac
}

# ===== 包检测函数（兼容 RPM 和 DEB）=====
# 注意: 优先用 dpkg 检测，因为 Ubuntu 上可能装了 rpm 命令但 MooseFS 实际是 DEB 包。
# 只要任一包管理器找到即视为已安装。
_mfs_check_pkg_installed() {
    local pkg="$1"
    if command -v dpkg >/dev/null 2>&1 && dpkg -s "${pkg}" >/dev/null 2>&1; then
        return 0
    fi
    if command -v rpm >/dev/null 2>&1 && rpm -q "${pkg}" >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

# ===== install 逻辑 =====
deploy_mfs_install() {
    local local_ip
    local_ip=$(get_local_ip)

    # 1. 检查是否跳过
    if _mfs_should_skip; then
        info "MooseFS disabled (MOOSEFS_ENABLED=no), skipping"
        return 0
    fi

    info "Configuring MooseFS on local machine"

    # 2. 验证包已由上游安装（支持 RPM 和 DEB）
    local missing=()
    for pkg in moosefs-master moosefs-chunkserver moosefs-client; do
        if ! _mfs_check_pkg_installed "${pkg}"; then
            missing+=("${pkg}")
        fi
    done
    if [ ${#missing[@]} -gt 0 ]; then
        error "MooseFS packages not installed: ${missing[*]}. Please install them before running this script. See deploy/moosefs/README.zh.md for dependency list."
    fi
    success "MooseFS packages verified"

    # 3. 验证 fuse3 依赖
    if ! _mfs_check_pkg_installed fuse3; then
        error "fuse3 package not installed. moosefs-client requires libfuse3.so.3. See deploy/moosefs/README.zh.md for installation."
    fi
    success "fuse3 dependency verified"

    # 4. 创建 chunkserver 存储目录
    info "Creating chunkserver storage directory: ${MFS_CHUNK_DIR}"
    mkdir -p "${MFS_CHUNK_DIR}"
    if id mfs >/dev/null 2>&1; then
        chown -R mfs:mfs "${MFS_CHUNK_DIR}"
    fi
    success "Chunkserver storage directory created"

    # 5. 创建挂载点目录
    info "Creating mount point: ${MFS_MOUNT_POINT}"
    mkdir -p "${MFS_MOUNT_POINT}"
    success "Mount point created"

    # 6. 配置 fuse 允许非 root 用户访问（allow_other）
    if [ -f /etc/fuse.conf ]; then
        if ! grep -q "user_allow_other" /etc/fuse.conf 2>/dev/null; then
            echo "user_allow_other" >> /etc/fuse.conf
            info "Enabled user_allow_other in /etc/fuse.conf"
        fi
    else
        echo "user_allow_other" > /etc/fuse.conf
        info "Created /etc/fuse.conf with user_allow_other"
    fi

    # 7. 生成 master 配置文件
    local mfs_conf_dir="/etc/mfs"
    mkdir -p "${mfs_conf_dir}"

    local master_host
    master_host=$(_mfs_resolve_master_host)
    [ -z "${master_host}" ] && master_host="${local_ip}"

    info "Generating mfsmaster.cfg in ${mfs_conf_dir}..."
    cat > "${mfs_conf_dir}/mfsmaster.cfg" <<EOF
# MooseFS Master configuration
DATA_PATH = /var/lib/mfs
EXPORTS_FILENAME = /etc/mfs/mfsexports.cfg
MATOML_LISTEN_HOST = *
MATOML_LISTEN_PORT = 9419
MATOCS_LISTEN_HOST = *
MATOCS_LISTEN_PORT = ${MFS_MASTER_PORT}
MATOCU_LISTEN_HOST = *
MATOCU_LISTEN_PORT = ${MFS_CLIENT_PORT}
EOF

    # 生成 mfsexports.cfg（允许所有客户端挂载，禁用 root 映射以透传真实 uid/gid）
    cat > "${mfs_conf_dir}/mfsexports.cfg" <<EOF
# Allow all clients to mount root with read/write
# maproot=0:0 disables root-to-mfs mapping, preserving real uid/gid
* / rw,maproot=0:0
EOF

    # 8. 生成 chunkserver 配置文件
    info "Generating mfschunkserver.cfg in ${mfs_conf_dir}..."
    cat > "${mfs_conf_dir}/mfschunkserver.cfg" <<EOF
# MooseFS Chunkserver configuration
MASTER_HOST = ${master_host}
MASTER_PORT = ${MFS_MASTER_PORT}
DATA_PATH = /var/lib/mfs
HDD_CONF_FILENAME = ${mfs_conf_dir}/mfshdd.cfg
CSSERV_LISTEN_PORT = ${MFS_CHUNK_PORT}
EOF

    # 生成 mfshdd.cfg（声明存储目录）
    cat > "${mfs_conf_dir}/mfshdd.cfg" <<EOF
# Chunkserver HDD directories
${MFS_CHUNK_DIR}
EOF

    # 统一设置配置文件权限：属主 root:mfs，权限 0640
    # 避免 umask 不确定导致权限不一致，同时仅允许 root 可写、mfs 组可读
    if id mfs >/dev/null 2>&1; then
        chown root:mfs "${mfs_conf_dir}" "${mfs_conf_dir}"/*.cfg
        chmod 0750 "${mfs_conf_dir}"
        chmod 0640 "${mfs_conf_dir}"/*.cfg
    else
        chmod 0750 "${mfs_conf_dir}"
        chmod 0640 "${mfs_conf_dir}"/*.cfg
    fi

    # 9. 初始化 metadata 目录（uninstall 清空了内容但保留目录）
    local mfs_data_dir="/var/lib/mfs"
    mkdir -p "${mfs_data_dir}"
    if id mfs >/dev/null 2>&1; then
        chown -R mfs:mfs "${mfs_data_dir}"
    fi
    success "MooseFS configuration files generated"

    # 10. 判断角色
    local is_master=false
    if _mfs_is_master; then
        is_master=true
    fi
    info "Node role: $([ "${is_master}" = "true" ] && echo "master" || echo "agent")"

    # 11. 生成 systemd unit 文件
    if _mfs_should_use_systemd; then
        info "systemd detected, generating unit files..."

        local systemd_dir="/etc/systemd/system"

        # Master 节点：生成 master + chunkserver + client unit
        if [ "${is_master}" = "true" ]; then
            cat > "${systemd_dir}/moosefs-master.service" <<EOF
[Unit]
Description=MooseFS Master Server
After=network.target
# 配合 client 的 PartOf 实现 stop 传播、start 拉起
Wants=moosefs-client.service
# StartLimit* 只在 [Unit] 段生效
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=forking
# ExecStartPre: 清理 reboot 后可能残留的锁文件（异常掉电/被杀时来不及清理）
ExecStartPre=-/bin/rm -f /var/lib/mfs/.mfsmaster.lock /var/lib/mfs/.bgwriter.lock
# ExecStart: 正常启动，失败时用 -a -i 从 changelog 恢复
# -i: 忽略 metadata 中的结构错误（如 flock_locks 引用已 closed 的文件）
ExecStart=/bin/bash -c '${MFS_BIN_MASTER} start || ${MFS_BIN_MASTER} -a -i start'
# ExecStop: 用 stop 优雅关闭写最终 metadata。client session 断开后 flock_locks 可能
# 引用已 closed 的文件，启动时 -i 标志会忽略此错误，无需从 changelog 恢复。
ExecStop=${MFS_BIN_MASTER} stop
# KillMode=mixed: SIGTERM 只发给主进程，不杀整个 cgroup（避免误杀 data writer）
KillMode=mixed
# Restart=always: SIGTERM 也会导致 master 退出（status=0），
# on-failure 不会重启正常退出的进程，用 always 确保任何异常退出都重启。
# systemctl stop 不会触发 Restart（systemd 明确区分 stop 和 crash）。
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

            cat > "${systemd_dir}/moosefs-chunkserver.service" <<EOF
[Unit]
Description=MooseFS Chunkserver
After=network.target moosefs-master.service

[Service]
Type=forking
ExecStart=${MFS_BIN_CHUNKSERVER} start
ExecStop=${MFS_BIN_CHUNKSERVER} stop
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

            cat > "${systemd_dir}/moosefs-client.service" <<EOF
[Unit]
Description=MooseFS Client Mount
After=network.target moosefs-master.service moosefs-chunkserver.service
Requires=moosefs-master.service
PartOf=moosefs-master.service
# burst=999: master 长时间不就绪时持续重试挂载
StartLimitIntervalSec=120
StartLimitBurst=999

[Service]
# mfsmount -f 前台运行，systemd 直接管理进程
Type=simple
# 清理 SIGKILL 残留的 dead 挂载（ENOTCONN 会导致 mount 失败循环）；- 使未挂载时不报错
ExecStartPre=-/bin/umount -l ${MFS_MOUNT_POINT}
ExecStart=${MFS_BIN_MOUNT} ${MFS_MOUNT_POINT} -H ${master_host} -P ${MFS_CLIENT_PORT} -f -o nonempty
ExecStop=/bin/umount -l ${MFS_MOUNT_POINT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

        else
            # Agent 节点：仅生成 chunkserver + client unit（不生成 master）
            cat > "${systemd_dir}/moosefs-chunkserver.service" <<EOF
[Unit]
Description=MooseFS Chunkserver
After=network.target

[Service]
Type=forking
ExecStart=${MFS_BIN_CHUNKSERVER} start
ExecStop=${MFS_BIN_CHUNKSERVER} stop
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

            cat > "${systemd_dir}/moosefs-client.service" <<EOF
[Unit]
Description=MooseFS Client Mount
After=network.target moosefs-chunkserver.service
# burst=999: master 长时间不就绪时持续重试挂载
StartLimitIntervalSec=120
StartLimitBurst=999

[Service]
Type=simple
# 清理 SIGKILL 残留的 dead 挂载（ENOTCONN 会导致 mount 失败循环）
ExecStartPre=-/bin/umount -l ${MFS_MOUNT_POINT}
ExecStart=${MFS_BIN_MOUNT} ${MFS_MOUNT_POINT} -H ${master_host} -P ${MFS_CLIENT_PORT} -f -o nonempty
ExecStop=/bin/umount -l ${MFS_MOUNT_POINT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
        fi

        # 健康检查 timer：mfsmount 进程可能存活但挂载 stale（FUSE 操作 hang），定期探测并自动 remount
        cat > "${systemd_dir}/moosefs-client-health.service" <<EOF
[Unit]
Description=MooseFS Client Mount Health Check

[Service]
Type=oneshot
TimeoutSec=10
# findmnt 校验 mfs# 挂载源（防降级为本地目录时误判健康）+ stat 探测响应（stale 会 hang），
# 任一失败则重启 client 触发 remount
ExecStart=/bin/bash -c 'findmnt -n -o SOURCE ${MFS_MOUNT_POINT} | grep -q "^mfs#" && timeout 10 stat ${MFS_MOUNT_POINT}/. >/dev/null 2>&1 || systemctl restart moosefs-client'
EOF

        cat > "${systemd_dir}/moosefs-client-health.timer" <<EOF
[Unit]
Description=Periodic MooseFS Client Mount Health Check

[Timer]
OnBootSec=30
OnUnitActiveSec=30
Unit=moosefs-client-health.service

[Install]
WantedBy=timers.target
EOF

        systemctl daemon-reload
        success "systemd unit files generated"

        # Master 节点：初始化 metadata 模板（启动前准备）
        if [ "${is_master}" = "true" ]; then
            if [ ! -f /var/lib/mfs/metadata.mfs ]; then
                # 检测角色互换：本机有 chunkserver 数据但无 master metadata，
                # 说明之前是 agent 节点，现在被配置为 master，原有数据无法继承
                if [ -d "${MFS_CHUNK_DIR}" ] && [ -n "$(ls -A "${MFS_CHUNK_DIR}" 2>/dev/null)" ]; then
                    warning "This node has chunkserver data but no master metadata."
                    warning "If this was previously an agent node and master role has changed,"
                    warning "  existing chunk data will become orphaned (new master = empty filesystem)."
                    warning "To use old data, copy /var/lib/mfs/metadata.mfs from the old master node."
                    warning "To start fresh, set MOOSEFS_PURGE_DATA=yes during uninstall to clear old data."
                fi
                info "Initializing master metadata template..."
                if [ -f /etc/mfs/metadata.mfs.empty ]; then
                    cp /etc/mfs/metadata.mfs.empty /var/lib/mfs/metadata.mfs
                    chown mfs:mfs /var/lib/mfs/metadata.mfs 2>/dev/null || true
                elif [ -f /var/lib/mfs/metadata.mfs.empty ]; then
                    cp /var/lib/mfs/metadata.mfs.empty /var/lib/mfs/metadata.mfs
                    chown mfs:mfs /var/lib/mfs/metadata.mfs 2>/dev/null || true
                fi
            fi
        fi

        success "MooseFS install completed! Use 'up' to start services."
        return 0
    fi

    success "MooseFS install completed!"
}

# ===== up 逻辑 =====
deploy_mfs_up() {
    if _mfs_should_skip; then
        info "MooseFS disabled (MOOSEFS_ENABLED=no), skipping"
        return 0
    fi

    local master_host
    master_host=$(_mfs_resolve_master_host)

    # systemd 模式：通过 systemctl enable --now 启动服务
    if _mfs_should_use_systemd; then
        # 确保有 master_host，为空时用本机 IP
        [ -z "${master_host}" ] && master_host="$(get_local_ip)"

        info "Starting MooseFS via systemd (enable --now)"

        # 清理可能的残留挂载（仅在未挂载时清理，避免重复 up 中断使用中的挂载）
        if ! grep -q "[[:space:]]${MFS_MOUNT_POINT}[[:space:]]" /proc/mounts 2>/dev/null; then
            umount -l ${MFS_MOUNT_POINT} 2>/dev/null || true
            if [ -d "${MFS_MOUNT_POINT}" ] && [ -n "$(ls -A ${MFS_MOUNT_POINT} 2>/dev/null)" ]; then
                warning "挂载点 ${MFS_MOUNT_POINT} 非空，可能存在残留文件。将以 -o nonempty 模式挂载。"
            fi
        fi

        local is_master=false
        if _mfs_is_master; then
            is_master=true
        fi
        info "Node role: $([ "${is_master}" = "true" ] && echo "master" || echo "agent")"

        if [ "${is_master}" = "true" ]; then
            # Master 节点
            info "Enabling and starting moosefs-master..."
            systemctl enable --now moosefs-master || error "Failed to start moosefs-master"

            # 等待 master 端口就绪
            info "Waiting for master port ${MFS_MASTER_PORT}..."
            local retries=0
            while [ ${retries} -lt 30 ]; do
                if echo > /dev/tcp/127.0.0.1/${MFS_MASTER_PORT} 2>/dev/null; then
                    success "Master port ${MFS_MASTER_PORT} is ready"
                    break
                fi
                retries=$((retries + 1))
                sleep 1
            done
            if [ ${retries} -ge 30 ]; then
                error "Master port ${MFS_MASTER_PORT} not ready after 30s"
            fi

            info "Enabling and starting moosefs-chunkserver..."
            systemctl enable --now moosefs-chunkserver || warning "Failed to start moosefs-chunkserver"

            info "Enabling and starting moosefs-client..."
            # 不 fallback 到直接 mfsmount：不受 systemd 管理，health timer 无法恢复
            if ! systemctl enable --now moosefs-client 2>/dev/null; then
                sleep 5
                systemctl start moosefs-client || error "Failed to start moosefs-client (run 'install' first if unit missing; check: journalctl -u moosefs-client -n 50)"
            fi

            # 启用健康检查 timer（检测 stale 挂载并自动 remount）
            systemctl enable --now moosefs-client-health.timer 2>/dev/null || warning "Failed to enable moosefs-client-health.timer"

            info "Setting goal=${MFS_GOAL} on ${MFS_MOUNT_POINT}..."
            ${MFS_BIN_SETGOAL} -r ${MFS_GOAL} ${MFS_MOUNT_POINT} 2>/dev/null || warning "Failed to set goal on ${MFS_MOUNT_POINT}"
        else
            # Agent 节点：等待 master 就绪（直接本机检测端口，不依赖 SSH）
            info "Waiting for master ${master_host}:${MFS_MASTER_PORT} to be ready..."
            local agent_retries=0
            while [ ${agent_retries} -lt 60 ]; do
                if echo > /dev/tcp/${master_host}/${MFS_MASTER_PORT} 2>/dev/null; then
                    success "Master is ready"
                    break
                fi
                agent_retries=$((agent_retries + 1))
                sleep 2
            done
            if [ ${agent_retries} -ge 60 ]; then
                warning "Master not ready after 120s, starting services anyway..."
            fi

            info "Enabling and starting moosefs-chunkserver..."
            systemctl enable --now moosefs-chunkserver || warning "Failed to start moosefs-chunkserver"

            info "Enabling and starting moosefs-client..."
            # 不 fallback 到直接 mfsmount：不受 systemd 管理，health timer 无法恢复
            if ! systemctl enable --now moosefs-client 2>/dev/null; then
                sleep 5
                systemctl start moosefs-client || error "Failed to start moosefs-client (run 'install' first if unit missing; check: journalctl -u moosefs-client -n 50)"
            fi

            # 启用健康检查 timer（检测 stale 挂载并自动 remount）
            systemctl enable --now moosefs-client-health.timer 2>/dev/null || warning "Failed to enable moosefs-client-health.timer"
        fi

        success "MooseFS systemd up completed!"
        return 0
    fi

    # 非 systemd 单机模式
    info "Starting MooseFS in single-node mode (non-systemd)"
    local local_ip
    local_ip=$(get_local_ip)
    local goal=1
    [ -n "${master_host}" ] && local_ip="${master_host}"

    # 先停止可能残留的进程
    ${MFS_BIN_MASTER} stop 2>/dev/null || true
    ${MFS_BIN_CHUNKSERVER} stop 2>/dev/null || true
    sleep 1

    # 首次启动需要初始化 metadata
    if [ ! -f /var/lib/mfs/metadata.mfs ]; then
        info "Initializing master metadata..."
        if [ -f /etc/mfs/metadata.mfs.empty ]; then
            cp /etc/mfs/metadata.mfs.empty /var/lib/mfs/metadata.mfs
            chown mfs:mfs /var/lib/mfs/metadata.mfs 2>/dev/null || true
        elif [ -f /var/lib/mfs/metadata.mfs.empty ]; then
            cp /var/lib/mfs/metadata.mfs.empty /var/lib/mfs/metadata.mfs
            chown mfs:mfs /var/lib/mfs/metadata.mfs 2>/dev/null || true
        else
            warning "metadata.mfs.empty not found, trying mfsmaster -a..."
            ${MFS_BIN_MASTER} -a 2>/dev/null || true
        fi
    fi

    info "Starting mfsmaster..."
    ${MFS_BIN_MASTER} start || error "Failed to start mfsmaster"

    info "Starting mfschunkserver..."
    ${MFS_BIN_CHUNKSERVER} start || error "Failed to start mfschunkserver"

    info "Mounting MooseFS..."
    ${MFS_BIN_MOUNT} ${MFS_MOUNT_POINT} -H ${local_ip} -P ${MFS_CLIENT_PORT} || error "Failed to mount MooseFS"

    info "Setting goal=${goal} on ${MFS_MOUNT_POINT}..."
    ${MFS_BIN_SETGOAL} -r ${goal} ${MFS_MOUNT_POINT} 2>/dev/null || warning "Failed to set goal on ${MFS_MOUNT_POINT}"

    success "MooseFS single-node deployment completed!"
}

# ===== restart 逻辑 =====
deploy_mfs_restart() {
    deploy_mfs_down
    sleep 2
    deploy_mfs_up
}

# ===== down 逻辑 =====
deploy_mfs_down() {
    if _mfs_should_skip; then
        info "MooseFS disabled (MOOSEFS_ENABLED=no), skipping"
        return 0
    fi

    local master_host
    master_host=$(_mfs_resolve_master_host)

    # systemd 模式：通过 systemctl stop 停止服务（不 disable，不删 unit 文件，留给 uninstall）
    if _mfs_should_use_systemd; then
        [ -z "${master_host}" ] && master_host="$(get_local_ip)"
        info "Stopping MooseFS via systemd (stop)"

        local is_master=false
        if _mfs_is_master; then
            is_master=true
        fi

        # 先停 health timer 再 lazy umount（避免 timer 在 umount 后触发 client restart 竞态）
        systemctl stop moosefs-client-health.timer 2>/dev/null || true
        umount -l ${MFS_MOUNT_POINT} 2>/dev/null || true

        # 停止顺序 client → chunkserver → master（master 先停会导致 client umount 失败）
        if [ "${is_master}" = "true" ]; then
            systemctl stop moosefs-client 2>/dev/null || true
            systemctl stop moosefs-chunkserver 2>/dev/null || true
            systemctl stop moosefs-master 2>/dev/null || true
        else
            systemctl stop moosefs-client 2>/dev/null || true
            systemctl stop moosefs-chunkserver 2>/dev/null || true
        fi

        # 清理残留 mfsmount 进程（须在 reset-failed 之前）
        local mfs_mount_pid
        mfs_mount_pid=$(pgrep -f "mfsmount.*${MFS_MOUNT_POINT}" 2>/dev/null || true)
        if [ -n "${mfs_mount_pid}" ]; then
            warning "mfsmount process still running (pid: ${mfs_mount_pid}), killing..."
            kill ${mfs_mount_pid} 2>/dev/null || true
            sleep 1
            kill -9 ${mfs_mount_pid} 2>/dev/null || true
        fi

        # 清理残留锁文件（保留 chunkserverid.mfs 等身份/索引文件）
        find "${MFS_CHUNK_DIR}" -name '.lock' -delete 2>/dev/null || true
        find /var/lib/mfs \( -name '.mfschunkserver.lock' -o -name '.mfsmaster.lock' -o -name '.bgwriter.lock' \) -delete 2>/dev/null || true

        if [ "${is_master}" = "true" ]; then
            systemctl reset-failed moosefs-master moosefs-chunkserver moosefs-client moosefs-client-health.service 2>/dev/null || true
        else
            systemctl reset-failed moosefs-chunkserver moosefs-client moosefs-client-health.service 2>/dev/null || true
        fi

        success "MooseFS systemd down completed!"
        return 0
    fi

    # 非 systemd 单机部署
    info "Stopping MooseFS in single-node mode (non-systemd)"
    umount -l ${MFS_MOUNT_POINT} 2>/dev/null || true
    ${MFS_BIN_CHUNKSERVER} stop 2>/dev/null || warning "Failed to stop mfschunkserver"
    ${MFS_BIN_MASTER} stop 2>/dev/null || warning "Failed to stop mfsmaster"

    # 确保残留 mfsmount 进程被清理
    local mfs_mount_pid
    mfs_mount_pid=$(pgrep -f "mfsmount.*${MFS_MOUNT_POINT}" 2>/dev/null || true)
    if [ -n "${mfs_mount_pid}" ]; then
        warning "mfsmount process still running (pid: ${mfs_mount_pid}), killing..."
        kill ${mfs_mount_pid} 2>/dev/null || true
        sleep 1
        kill -9 ${mfs_mount_pid} 2>/dev/null || true
    fi

    # 清理残留锁文件（保留 chunkserverid.mfs 等身份/索引文件）
    find "${MFS_CHUNK_DIR}" -name '.lock' -delete 2>/dev/null || true
    find /var/lib/mfs \( -name '.mfschunkserver.lock' -o -name '.mfsmaster.lock' -o -name '.bgwriter.lock' \) -delete 2>/dev/null || true

    success "MooseFS single-node stopped"
}

# ===== uninstall 逻辑 =====
deploy_mfs_uninstall() {
    if _mfs_should_skip; then
        info "MooseFS disabled (MOOSEFS_ENABLED=no), skipping"
        return 0
    fi

    info "Uninstalling MooseFS"

    # 判断角色
    local is_master=false
    if _mfs_is_master; then
        is_master=true
    fi

    # 先停 health timer，避免清理挂载点时探针失败触发 client restart
    systemctl stop moosefs-client-health.timer 2>/dev/null || true
    # lazy umount（stale 挂载点上的操作会 hang）
    umount -l ${MFS_MOUNT_POINT} 2>/dev/null || true

    # 如果 systemd 已注册：停止服务 + 删除 unit 文件
    if _mfs_should_use_systemd; then
        info "Stopping services and removing systemd unit files..."
        if [ "${is_master}" = "true" ]; then
            # Master：disable + 删除 unit
            systemctl disable --now moosefs-master moosefs-chunkserver moosefs-client moosefs-client-health.timer 2>/dev/null || true
            rm -f /etc/systemd/system/moosefs-master.service
            rm -f /etc/systemd/system/moosefs-chunkserver.service
            rm -f /etc/systemd/system/moosefs-client.service
            rm -f /etc/systemd/system/moosefs-client-health.service
            rm -f /etc/systemd/system/moosefs-client-health.timer
            # reset-failed 清除 systemd 残留 failed 状态，避免 status 误报
            systemctl reset-failed moosefs-master moosefs-chunkserver moosefs-client moosefs-client-health.service 2>/dev/null || true
        else
            # Agent：disable + 删除 unit
            systemctl disable --now moosefs-chunkserver moosefs-client moosefs-client-health.timer 2>/dev/null || true
            rm -f /etc/systemd/system/moosefs-chunkserver.service
            rm -f /etc/systemd/system/moosefs-client.service
            rm -f /etc/systemd/system/moosefs-client-health.service
            rm -f /etc/systemd/system/moosefs-client-health.timer
            systemctl reset-failed moosefs-chunkserver moosefs-client moosefs-client-health.service 2>/dev/null || true
        fi
        systemctl daemon-reload
        success "systemd services stopped and unit files removed"
    else
        # 非 systemd 模式：手动停止服务
        info "Stopping MooseFS services..."
        ${MFS_BIN_CHUNKSERVER} stop 2>/dev/null || true
        ${MFS_BIN_MASTER} stop 2>/dev/null || true

        # 清理残留 mfsmount 进程
        local mfs_mount_pid
        mfs_mount_pid=$(pgrep -f "mfsmount.*${MFS_MOUNT_POINT}" 2>/dev/null || true)
        if [ -n "${mfs_mount_pid}" ]; then
            warning "mfsmount process still running (pid: ${mfs_mount_pid}), killing..."
            kill ${mfs_mount_pid} 2>/dev/null || true
            sleep 1
            kill -9 ${mfs_mount_pid} 2>/dev/null || true
        fi
        success "MooseFS services stopped"
    fi

    # RPM 包由上游安装，uninstall 不负责卸载

    # 清理配置文件（每次 uninstall 都清理，install 时重新生成）
    info "Cleaning up configuration files..."
    rm -f /etc/mfs/mfsmaster.cfg /etc/mfs/mfsexports.cfg /etc/mfs/mfschunkserver.cfg /etc/mfs/mfshdd.cfg 2>/dev/null || true

    # 数据清理：默认保留数据，MOOSEFS_PURGE_DATA=yes 时彻底清理
    if [ "${MOOSEFS_PURGE_DATA}" = "yes" ]; then
        info "MOOSEFS_PURGE_DATA=yes, purging all data..."
        # 注意：rm -rf dir/* 不匹配隐藏文件（.开头），需用 find 清理全部内容
        find "${MFS_CHUNK_DIR}" -mindepth 1 -delete 2>/dev/null || true
        find /var/lib/mfs -type f -delete 2>/dev/null || true
        success "All data purged"
    else
        info "MOOSEFS_PURGE_DATA=no, preserving data for reinstall recovery"
        # 删除运行时状态文件（chunkserver 重启后会重新注册并扫描上报已有 chunk）
        find "${MFS_CHUNK_DIR}" \( -name '.metaid' -o -name '.chunkdb' -o -name '.lock' \) -delete 2>/dev/null || true
        # 清理 /var/lib/mfs 下的运行时状态文件（保留 master metadata 和 chunk 数据）
        find /var/lib/mfs \( -name 'chunkserverid.mfs' -o -name '.mfschunkserver.lock' -o -name '.mfsmaster.lock' -o -name '.bgwriter.lock' \) -delete 2>/dev/null || true
        # 清理旧版可能的锁文件残留（/var/run/mfs/）
        rm -f /var/run/mfs/mfsmaster.lock /var/run/mfs/mfschunkserver.lock 2>/dev/null || true
        success "Data preserved (chunkserver chunks + master metadata), runtime state files cleared"
    fi

    success "MooseFS uninstall completed!"
}

# ===== status 逻辑 =====
# 仅只读探测服务状态，不启停服务
# 输出格式：每行 moosefs|<service>|<state>|<detail>|<version>
# state: running / stopped / failed / disabled
# version: 从 mfsmaster -v 输出提取，获取失败显示 -
deploy_mfs_status() {
    _mfs_load_config

    # 探测 MooseFS 版本号：mfsmaster -v 输出 "version: 4.59.2-1 ; build: 2106"
    local mfs_ver="-"
    if [ -x "${MFS_BIN_MASTER}" ]; then
        mfs_ver=$("${MFS_BIN_MASTER}" -v 2>/dev/null | head -n1 | sed -E 's/^version:[[:space:]]*//' | awk -F' ;' '{print $1}' || true)
        [ -z "${mfs_ver}" ] && mfs_ver="-"
    fi

    # 全局禁用：输出 disabled，return 0
    if _mfs_should_skip; then
        echo "moosefs|-|disabled|MOOSEFS_ENABLED=no|${mfs_ver}"
        return 0
    fi

    # 角色判定（复用 _mfs_is_master）
    local is_master=false
    if _mfs_is_master; then
        is_master=true
    fi
    local role="agent"
    [ "${is_master}" = "true" ] && role="master"

    # 通用：检测挂载点是否已挂载
    # mountpoint 不可用时回退读 /proc/mounts
    local mount_detail=""
    if command -v mountpoint >/dev/null 2>&1; then
        if mountpoint -q "${MFS_MOUNT_POINT}" 2>/dev/null; then
            mount_detail=";mounted:${MFS_MOUNT_POINT}"
        fi
    else
        if grep -q "[[:space:]]${MFS_MOUNT_POINT}[[:space:]]" /proc/mounts 2>/dev/null; then
            mount_detail=";mounted:${MFS_MOUNT_POINT}"
        fi
    fi

    # 进程模式（非 systemd）的 pgrep 检测助手
    # 返回：0 运行中，1 未运行
    _mfs_status_pgrep_running() {
        local bin_name="$1"
        if command -v pgrep >/dev/null 2>&1; then
            pgrep -x "${bin_name}" >/dev/null 2>&1
        else
            # 回退：ps -ef | grep <bin_name> | grep -v grep
            # 用 [b]in_name 模式避免匹配 grep 自身，不加 $ 锚定（进程名后通常带参数）
            ps -ef 2>/dev/null | grep -v grep | grep -q "[${bin_name:0:1}]${bin_name:1}"
        fi
    }

    local rc=0   # 整体返回码：全 running→0，有 failed→1，全 stopped→0

    if _mfs_should_use_systemd; then
        # ----- systemd 模式 -----
        local units=()
        if [ "${is_master}" = "true" ]; then
            units=(moosefs-master moosefs-chunkserver moosefs-client moosefs-client-health.timer)
        else
            units=(moosefs-chunkserver moosefs-client moosefs-client-health.timer)
        fi

        for unit in "${units[@]}"; do
            local state="stopped"
            local detail="inactive"
            # unit 文件已删除时（uninstall 后）判为 stopped；unit 名无后缀时补 .service
            local unit_file="/etc/systemd/system/${unit}"
            [[ "${unit}" != *.* ]] && unit_file="${unit_file}.service"
            if [ ! -f "${unit_file}" ]; then
                state="stopped"
                detail="unit not found"
            elif systemctl is-failed "${unit}" >/dev/null 2>&1; then
                state="failed"
                detail="failed"
                rc=1
            elif systemctl is-active "${unit}" >/dev/null 2>&1; then
                state="running"
                detail="active"
            else
                state="stopped"
                detail="inactive"
            fi
            echo "moosefs|${unit}|${state}|${detail}${mount_detail}|${mfs_ver}"
        done

        return ${rc}
    fi

    # ----- 进程模式（非 systemd）-----
    # 用 _mfs_bin 取二进制名，pgrep 按进程名匹配
    local procs=()
    if [ "${is_master}" = "true" ]; then
        procs=("mfsmaster" "mfschunkserver" "mfsmount")
    else
        procs=("mfschunkserver" "mfsmount")
    fi

    for bin in "${procs[@]}"; do
        local state="stopped"
        local detail="inactive"
        if _mfs_status_pgrep_running "${bin}"; then
            state="running"
            detail="active"
        else
            state="stopped"
            detail="inactive"
        fi
        echo "moosefs|${bin}|${state}|${detail}${mount_detail}|${mfs_ver}"
    done

    return ${rc}
}

# ===== 参数解析 =====
parse_args() {
    local i=0
    local args=("$@")
    while [ $i -lt ${#args[@]} ]; do
        case "${args[$i]}" in
            up|down|restart|install|uninstall|status)
                CMD="${args[$i]}"
                i=$((i+1))
                ;;
            --ip)
                BIND_IP="${args[$((i+1))]}"
                i=$((i+2))
                ;;
            -h|--help)
                print_help
                ;;
            *)
                error "Invalid Args: ${args[$i]}"
                ;;
        esac
    done

    if [ -z "${CMD:-}" ]; then
        error "Command not specified! Use 'up', 'down', 'install' or 'uninstall'"
        exit 1
    fi

    info "Executing command: $*"
    info "CMD=${CMD}"
    if [ -n "${BIND_IP}" ]; then
        info "BIND_IP=${BIND_IP}"
    fi
}

# ===== 帮助信息 =====
print_help() {
    cat << EOF
Usage: ./$(basename "$0") [COMMAND] [OPTIONS]

独立部署 MooseFS 分布式存储集群。
本脚本不依赖 deploy 目录下其他文件，可独立执行。

Commands (Required):
  up        启动 MooseFS 集群（systemd 模式下执行 systemctl enable --now）
  down      停止 MooseFS 集群（systemd 模式下执行 systemctl stop）
  restart   重启 MooseFS 集群
  install   验证软件包已安装（RPM/DEB） + 生成配置 + systemd 模式下生成 unit（不启动，由 up 启动）
  uninstall 停止服务 + 清理配置、数据和 systemd unit（不卸载软件包，可重新 install 还原）

Options:
  --ip IP            指定本机使用的 IP 地址（多网卡环境必用）。
                     指定后 get_local_ip / is_local_host 使用该 IP，避免自动探测不准。
                     指定的 IP 必须是本机真实持有的 IP，否则报错退出。
                     不指定时自动探测（hostname -I / ip addr / ifconfig）。
  -h, --help         显示帮助信息

Environment Variables:
  MOOSEFS_MASTER_HOST    Master 节点地址（systemd 模式下区分 master/agent 角色）
                         默认从 deploy/config.yaml 的 master_nodes 第一个 IP 获取
  MOOSEFS_ENABLED        是否启用 MooseFS（auto/yes/no，默认 auto）
                         auto/yes: 默认部署分布式文件系统
                         no:       关闭分布式文件系统（使用本地文件系统）
  MOOSEFS_USE_SYSTEMD    是否使用 systemd（auto/yes/no，默认 auto）
                         auto: 自动检测（command -v systemctl + /run/systemd/system）
                         yes:  强制使用（不可用则报错）
                         no:   强制禁用（使用直接脚本执行）
  MFS_MASTER_PORT        Master 服务端口（默认 9420）
  MFS_CHUNK_PORT         Chunkserver 端口（默认 9422）
  MFS_CLIENT_PORT        Client (mfsmount) 端口（默认 9421）
  MFS_CHUNK_DIR          Chunkserver 数据目录（默认 /data/mfschunks）
  MFS_MOUNT_POINT        共享挂载点路径（默认 /home/agentos/users）
  MFS_GOAL               数据副本数（多机默认 2，单机自动设为 1）

Configuration File:
  ${SCRIPT_DIR}/moosefs.conf  MooseFS 配置文件，可通过环境变量覆盖

Deployment Modes:
  1. systemd 模式: 默认部署（install=配置+unit生成，up=enable--now，down=stop，uninstall=停止+清理）
  2. 关闭: MOOSEFS_ENABLED=no，不部署 MooseFS（使用本地文件系统）

Examples:
  # systemd 模式（默认，从 config.yaml 获取 master IP）
  ./$(basename "$0") install
  ./$(basename "$0") up
  ./$(basename "$0") down
  ./$(basename "$0") uninstall

  # 指定本机 IP（多网卡环境）
  ./$(basename "$0") up --ip 192.168.1.1

  MOOSEFS_ENABLED=no ./$(basename "$0") up                            # 关闭 MooseFS 部署

注意:
  - install 需要在每台目标主机上执行（每台主机都需配置）
  - MooseFS 软件包（RPM/DEB）需由上游预装（见 deploy/moosefs/README.zh.md）
  - master IP 从 deploy/config.yaml 的 master_nodes 第一个 IP 获取
EOF
    exit 0
}

# ===== main 入口 =====
main() {
    _mfs_load_config
    parse_args "$@"
    deploy_mfs_${CMD}
}

main "$@"
