#!/usr/bin/env bash
set -euo >/dev/null 2>&1

# ============================================================
# MooseFS 分布式存储部署独立脚本
# 完全自包含，不依赖任何其他文件
# 用法:
#   ./moosefs_deploy.sh install
#   ./moosefs_deploy.sh up --hosts 192.168.1.1,192.168.1.2
#   ./moosefs_deploy.sh down --hosts 192.168.1.1,192.168.1.2
#   ./moosefs_deploy.sh uninstall
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CLUSTER_HOSTS=""
CMD=""
AGENTOS_SSH_KEY="${AGENTOS_SSH_KEY:-/root/.ssh/agent_key}"
SSH_OPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"

# ===== 日志函数 =====
info()    { echo -e "\033[36m=== $@ ===\033[0m"; }
success() { echo -e "\033[32m✅ $@\033[0m"; }
warning() { echo -e "\033[33m⚠️  $@\033[0m"; }
error()   { echo -e "\033[31m❌ $@\033[0m"; exit 1; }

# ===== SSH 工具函数 =====
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

exec_on_host() {
    local host="$1"
    shift
    if is_local_host "${host}"; then
        bash -c "$*"
    else
        ssh ${SSH_OPTS} root@${host} "$*"
    fi
}

copy_to_host() {
    local host="$1"
    local src="$2"
    local dst="$3"
    if is_local_host "${host}"; then
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
    else
        scp ${SSH_OPTS} -r "${src}" "root@${host}:${dst}"
    fi
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
_mfs_is_master() {
    local local_ip
    local_ip=$(get_local_ip)

    # SSH 多机模式（CLUSTER_HOSTS 有 2+ IP）
    local host_count=0
    if [ -n "${CLUSTER_HOSTS:-}" ]; then
        local IFS_OLD="${IFS}"
        IFS=','
        read -ra _hosts_arr <<< "${CLUSTER_HOSTS}"
        IFS="${IFS_OLD}"
        host_count=${#_hosts_arr[@]}
    fi

    if [ "${host_count}" -ge 2 ]; then
        local first_ip="${_hosts_arr[0]}"
        if [ "${local_ip}" = "${first_ip}" ] || is_local_host "${first_ip}"; then
            return 0
        fi
        return 1
    fi

    # systemd 模式（无 --hosts 或仅 1 IP）
    if [ -z "${MOOSEFS_MASTER_HOST:-}" ]; then
        warning "MOOSEFS_MASTER_HOST not set, cannot determine role"
        return 1
    fi
    if [ "${local_ip}" = "${MOOSEFS_MASTER_HOST}" ] || is_local_host "${MOOSEFS_MASTER_HOST}"; then
        return 0
    fi

    return 1
}

# ===== MOOSEFS_MASTER_HOST 解析与优先级 =====
_mfs_resolve_master_host() {
    local master_host=""
    local host_count=0

    if [ -n "${CLUSTER_HOSTS:-}" ]; then
        local IFS_OLD="${IFS}"
        IFS=','
        read -ra _hosts_arr <<< "${CLUSTER_HOSTS}"
        IFS="${IFS_OLD}"
        host_count=${#_hosts_arr[@]}
    fi

    if [ "${host_count}" -ge 2 ]; then
        master_host="${_hosts_arr[0]}"
        if [ -n "${MOOSEFS_MASTER_HOST:-}" ] && [ "${MOOSEFS_MASTER_HOST}" != "${master_host}" ]; then
            warning "MOOSEFS_MASTER_HOST=${MOOSEFS_MASTER_HOST} is overridden by --hosts first IP: ${master_host}"
        fi
    else
        master_host="${MOOSEFS_MASTER_HOST:-}"
    fi

    echo "${master_host}"
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

# ===== 获取 cluster host 列表数组 =====
_mfs_get_host_list() {
    if [ -n "${CLUSTER_HOSTS:-}" ]; then
        echo "${CLUSTER_HOSTS}" | tr ',' ' '
    fi
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
        error "MooseFS packages not installed: ${missing[*]}. Please install them before running this script. See deploy/moosefs/README.md for dependency list."
    fi
    success "MooseFS packages verified"

    # 3. 验证 fuse3 依赖
    if ! _mfs_check_pkg_installed fuse3; then
        error "fuse3 package not installed. moosefs-client requires libfuse3.so.3. See deploy/moosefs/README.md for installation."
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

    # 7. 生成 chunkserver 配置文件
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

    # 8. 初始化 metadata 目录（uninstall 清空了内容但保留目录）
    local mfs_data_dir="/var/lib/mfs"
    mkdir -p "${mfs_data_dir}"
    if id mfs >/dev/null 2>&1; then
        chown -R mfs:mfs "${mfs_data_dir}"
    fi
    success "MooseFS configuration files generated"

    # 9. 判断角色
    local is_master=false
    if _mfs_is_master; then
        is_master=true
    fi
    info "Node role: $([ "${is_master}" = "true" ] && echo "master" || echo "agent")"

    # 10. 生成 systemd unit 文件
    if _mfs_should_use_systemd; then
        info "systemd detected, generating unit files..."

        local systemd_dir="/etc/systemd/system"

        # Master 节点：生成 master + chunkserver + client unit
        if [ "${is_master}" = "true" ]; then
            cat > "${systemd_dir}/moosefs-master.service" <<EOF
[Unit]
Description=MooseFS Master Server
After=network.target

[Service]
Type=forking
ExecStart=${MFS_BIN_MASTER} start
ExecStop=${MFS_BIN_MASTER} stop
Restart=on-failure

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

[Service]
Type=oneshot
ExecStart=${MFS_BIN_MOUNT} ${MFS_MOUNT_POINT} -H ${master_host} -P ${MFS_CLIENT_PORT}
ExecStop=/bin/umount ${MFS_MOUNT_POINT}
RemainAfterExit=yes

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

[Service]
Type=oneshot
ExecStart=${MFS_BIN_MOUNT} ${MFS_MOUNT_POINT} -H ${master_host} -P ${MFS_CLIENT_PORT}
ExecStop=/bin/umount ${MFS_MOUNT_POINT}
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
        fi

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

    local host_count=0
    if [ -n "${CLUSTER_HOSTS:-}" ]; then
        local IFS_OLD="${IFS}"
        IFS=','
        read -ra _hosts_arr <<< "${CLUSTER_HOSTS}"
        IFS="${IFS_OLD}"
        host_count=${#_hosts_arr[@]}
    fi

    # SSH 多机模式（CLUSTER_HOSTS 有 2+ IP，且非 systemd 模式）
    if [ "${host_count}" -ge 2 ] && ! _mfs_should_use_systemd; then
        info "Starting MooseFS in SSH multi-node mode"
        info "Master host: ${master_host}"
        info "Total hosts: ${host_count}"

        # 启动 master
        info "Starting mfsmaster on ${master_host}..."
        exec_on_host "${master_host}" "${MFS_BIN_MASTER} start" || error "Failed to start mfsmaster on ${master_host}"

        # 等待 master 端口可连接
        info "Waiting for master port ${MFS_MASTER_PORT} on ${master_host}..."
        local retries=0
        while [ ${retries} -lt 30 ]; do
            if exec_on_host "${master_host}" "echo > /dev/tcp/${master_host}/${MFS_MASTER_PORT}" 2>/dev/null; then
                success "Master port ${MFS_MASTER_PORT} is ready on ${master_host}"
                break
            fi
            retries=$((retries + 1))
            sleep 1
        done
        if [ ${retries} -ge 30 ]; then
            error "Master port ${MFS_MASTER_PORT} not ready on ${master_host} after 30s"
        fi

        # 启动所有节点的 chunkserver
        for host in "${_hosts_arr[@]}"; do
            info "Starting mfschunkserver on ${host}..."
            exec_on_host "${host}" "${MFS_BIN_CHUNKSERVER} start" || error "Failed to start mfschunkserver on ${host}"
        done

        # 等待 chunkserver 注册
        info "Waiting for chunkservers to register..."
        sleep 2

        # 挂载所有节点
        for host in "${_hosts_arr[@]}"; do
            info "Mounting MooseFS on ${host}..."
            exec_on_host "${host}" "${MFS_BIN_MOUNT} ${MFS_MOUNT_POINT} -H ${master_host} -P ${MFS_CLIENT_PORT}" || warning "Failed to mount MooseFS on ${host}"
        done

        # 设置 goal
        info "Setting goal=${MFS_GOAL} on ${MFS_MOUNT_POINT}..."
        exec_on_host "${master_host}" "${MFS_BIN_SETGOAL} -r ${MFS_GOAL} ${MFS_MOUNT_POINT}" 2>/dev/null || warning "Failed to set goal on ${MFS_MOUNT_POINT}"

        success "MooseFS SSH multi-node deployment completed!"
        return 0
    fi

    # systemd 模式：通过 systemctl enable --now 启动服务
    if _mfs_should_use_systemd; then
        # 确保有 master_host，为空时用本机 IP
        [ -z "${master_host}" ] && master_host="$(get_local_ip)"

        info "Starting MooseFS via systemd (enable --now)"

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
            systemctl enable --now moosefs-client 2>/dev/null || {
                warning "moosefs-client.service failed, trying direct mfsmount..."
                ${MFS_BIN_MOUNT} ${MFS_MOUNT_POINT} -H ${master_host} -P ${MFS_CLIENT_PORT} || warning "Direct mfsmount also failed"
            }

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
            systemctl enable --now moosefs-client 2>/dev/null || {
                warning "moosefs-client.service failed, trying direct mfsmount..."
                ${MFS_BIN_MOUNT} ${MFS_MOUNT_POINT} -H ${master_host} -P ${MFS_CLIENT_PORT} || warning "Direct mfsmount also failed"
            }
        fi

        success "MooseFS systemd up completed!"
        return 0
    fi

    # 非 systemd 的 SSH 单机部署（CLUSTER_HOSTS 仅 1 IP）
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
    ${MFS_BIN_MOUNT} ${MFS_MOUNT_POINT} -H ${local_ip} -P ${MFS_CLIENT_PORT} || warning "Failed to mount MooseFS"

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

    local host_count=0
    if [ -n "${CLUSTER_HOSTS:-}" ]; then
        local IFS_OLD="${IFS}"
        IFS=','
        read -ra _hosts_arr <<< "${CLUSTER_HOSTS}"
        IFS="${IFS_OLD}"
        host_count=${#_hosts_arr[@]}
    fi

    # SSH 多机模式
    if [ "${host_count}" -ge 2 ] && ! _mfs_should_use_systemd; then
        info "Stopping MooseFS in SSH multi-node mode"

        # SSH 到所有节点执行 umount + mfschunkserver stop
        for host in "${_hosts_arr[@]}"; do
            info "Unmounting and stopping chunkserver on ${host}..."
            exec_on_host "${host}" "umount ${MFS_MOUNT_POINT}" 2>/dev/null || warning "Failed to umount on ${host}"
            exec_on_host "${host}" "${MFS_BIN_CHUNKSERVER} stop" 2>/dev/null || warning "Failed to stop mfschunkserver on ${host}"
        done

        # SSH 到 master 节点执行 mfsmaster stop
        info "Stopping mfsmaster on ${master_host}..."
        exec_on_host "${master_host}" "${MFS_BIN_MASTER} stop" 2>/dev/null || warning "Failed to stop mfsmaster on ${master_host}"

        success "MooseFS SSH multi-node stopped"
        return 0
    fi

    # systemd 模式：通过 systemctl disable --now 停止服务
    if _mfs_should_use_systemd; then
        [ -z "${master_host}" ] && master_host="$(get_local_ip)"
        info "Stopping MooseFS via systemd (disable --now)"

        # 先 lazy umount（防止 master 已停止时 FUSE 挂载点 stale 导致 hang）
        umount -l ${MFS_MOUNT_POINT} 2>/dev/null || true

        local is_master=false
        if _mfs_is_master; then
            is_master=true
        fi

        if [ "${is_master}" = "true" ]; then
            systemctl disable --now moosefs-master moosefs-chunkserver moosefs-client 2>/dev/null || true
        else
            systemctl disable --now moosefs-chunkserver moosefs-client 2>/dev/null || true
        fi

        # 清理残留 mfsmount 进程
        local mfs_mount_pid
        mfs_mount_pid=$(pgrep -f "mfsmount.*${MFS_MOUNT_POINT}" 2>/dev/null || true)
        if [ -n "${mfs_mount_pid}" ]; then
            warning "mfsmount process still running (pid: ${mfs_mount_pid}), killing..."
            kill ${mfs_mount_pid} 2>/dev/null || true
            sleep 1
            kill -9 ${mfs_mount_pid} 2>/dev/null || true
        fi

        success "MooseFS systemd down completed!"
        return 0
    fi

    # 非 systemd 的 SSH 单机部署
    info "Stopping MooseFS in single-node mode (non-systemd)"
    umount ${MFS_MOUNT_POINT} 2>/dev/null || true
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

    # 先 lazy umount（防止 master 已停止时 FUSE 挂载点 stale 导致后续操作 hang）
    umount -l ${MFS_MOUNT_POINT} 2>/dev/null || true

    # 如果 systemd 已注册：停止服务 + 删除 unit 文件
    if _mfs_should_use_systemd; then
        info "Stopping services and removing systemd unit files..."
        if [ "${is_master}" = "true" ]; then
            # Master：disable + 删除三个 unit
            systemctl disable --now moosefs-master moosefs-chunkserver moosefs-client 2>/dev/null || true
            rm -f /etc/systemd/system/moosefs-master.service
            rm -f /etc/systemd/system/moosefs-chunkserver.service
            rm -f /etc/systemd/system/moosefs-client.service
        else
            # Agent：disable + 删除两个 unit
            systemctl disable --now moosefs-chunkserver moosefs-client 2>/dev/null || true
            rm -f /etc/systemd/system/moosefs-chunkserver.service
            rm -f /etc/systemd/system/moosefs-client.service
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
        # 删除 chunkserver 运行时状态文件，避免重新注册时 ID/索引/锁冲突
        # chunkserver 启动时会重新从 master 获取 ID 并扫描已有 chunk 数据上报
        find "${MFS_CHUNK_DIR}" \( -name '.metaid' -o -name '.chunkdb' -o -name '.lock' \) -delete 2>/dev/null || true
        # 清理 /var/lib/mfs 下的运行时状态文件（保留 master metadata 和 chunk 数据）
        find /var/lib/mfs \( -name 'chunkserverid.mfs' -o -name '.mfschunkserver.lock' -o -name '.mfsmaster.lock' -o -name '.bgwriter.lock' \) -delete 2>/dev/null || true
        # 清理旧版可能的锁文件残留（/var/run/mfs/）
        rm -f /var/run/mfs/mfsmaster.lock /var/run/mfs/mfschunkserver.lock 2>/dev/null || true
        success "Data preserved (chunkserver chunks + master metadata), runtime state files cleared"
    fi

    success "MooseFS uninstall completed!"
}

# ===== 参数解析 =====
parse_args() {
    local i=0
    local args=("$@")
    while [ $i -lt ${#args[@]} ]; do
        case "${args[$i]}" in
            up|down|restart|install|uninstall)
                CMD="${args[$i]}"
                i=$((i+1))
                ;;
            --hosts)
                CLUSTER_HOSTS="${args[$((i+1))]}"
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

    # install/uninstall 仅在本机执行，不需要 CLUSTER_HOSTS
    # up/down 在 systemd 模式下也不需要 CLUSTER_HOSTS（从 config.yaml 获取 master IP）
    # 仅在非 systemd 的 up/down 时需要 CLUSTER_HOSTS
    if [[ "${CMD}" != "install" && "${CMD}" != "uninstall" ]]; then
        if [ -z "${CLUSTER_HOSTS:-}" ]; then
            CLUSTER_HOSTS=$(get_local_ip)
            info "CLUSTER_HOSTS not specified, using local IP: ${CLUSTER_HOSTS}"
        fi
    fi

    info "Executing command: $*"
    info "CMD=${CMD}"
    if [[ "${CMD}" != "install" && "${CMD}" != "uninstall" ]]; then
        info "CLUSTER_HOSTS=${CLUSTER_HOSTS}"
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
  down      停止 MooseFS 集群（systemd 模式下执行 systemctl disable --now）
  restart   重启 MooseFS 集群
  install   验证 RPM 已安装 + 生成配置 + systemd 模式下生成 unit（不启动，由 up 启动）
  uninstall 停止服务 + 清理配置、数据和 systemd unit（不卸载 RPM，可重新 install 还原）

Options:
  --hosts HOSTS      目标主机IP列表，逗号分隔。第一个IP为master节点，其余为agent节点
                     仅 up/down/restart 命令需要，install/uninstall 忽略此参数
                     单机: --hosts 192.168.1.1
                     多机: --hosts 192.168.1.1,192.168.1.2,192.168.1.3
                     不指定时默认使用本机IP
  -h, --help         显示帮助信息

Environment Variables:
  MOOSEFS_MASTER_HOST    Master 节点地址（systemd 模式下区分 master/agent 角色）
                         SSH 多机模式下自动取 --hosts 第一个 IP，此配置被覆盖
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
  AGENTOS_SSH_KEY        SSH 私钥路径（默认 /root/.ssh/agent_key）

Configuration File:
  ${SCRIPT_DIR}/moosefs.conf  MooseFS 配置文件，可通过环境变量覆盖

Deployment Modes:
  1. SSH 多机模式: --hosts 指定 2+ IP，Master 取第一个 IP（非 systemd，install+up/down+uninstall）
  2. systemd 模式: 无 --hosts，默认部署（install=配置+unit生成，up=enable--now，down=disable--now，uninstall=停止+清理）
  3. 关闭: MOOSEFS_ENABLED=no，不部署 MooseFS（使用本地文件系统）

Examples:
  # systemd 模式（默认，从 config.yaml 获取 master IP）
  ./$(basename "$0") install
  ./$(basename "$0") up
  ./$(basename "$0") down
  ./$(basename "$0") uninstall

  # 非 systemd SSH 多机模式
  ./$(basename "$0") install                                          # 本机生成配置
  ./$(basename "$0") up --hosts 192.168.1.1,192.168.1.2,192.168.1.3  # 多机启动集群
  ./$(basename "$0") down --hosts 192.168.1.1                        # 停止集群
  ./$(basename "$0") uninstall                                        # 本机清理配置和数据
  MOOSEFS_ENABLED=no ./$(basename "$0") up                            # 关闭 MooseFS 部署

注意:
  - 部署机器到所有目标主机需配置SSH免密登录（仅 SSH 多机模式）
  - install 需要在每台目标主机上执行（每台主机都需配置）
  - MooseFS RPM 包需由上游预装（见 deploy/moosefs/README.md）
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
