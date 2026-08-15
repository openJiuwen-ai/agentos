#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# jiuwenbox 部署脚本（自包含，对齐 yuanrong_deploy.sh）
# 优先使用 systemd 托管（Restart=on-failure）；无 systemd 时回退 nohup。
# 用法:
#   ./jiuwenbox_deploy.sh up --hosts 192.168.1.1,192.168.1.2
#   ./jiuwenbox_deploy.sh down --hosts 192.168.1.1
#   ./jiuwenbox_deploy.sh up                    # 默认本机
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

CLUSTER_HOSTS=""
CMD=""
PYTHON_CONFIG=""
SSH_OPTS="${JIUWENBOX_SSH_OPTS:--o StrictHostKeyChecking=accept-new -o ConnectTimeout=10}"
REMOTE_STAGE="${JIUWENBOX_REMOTE_STAGE:-/tmp/agentos_jiuwenbox}"
POLICY_TEMPLATE="${SCRIPT_DIR}/default-policy.yaml"

RUN_DIR="${JIUWENBOX_RUN_DIR:-/tmp/jiuwenbox}"
LOG_FILE="${RUN_DIR}/jiuwenbox.log"
DEFAULT_LISTEN="unix:///run/jiuwenbox/jiuwenbox.sock"
LISTEN_URI="${JIUWENBOX_LISTEN:-$DEFAULT_LISTEN}"
UDS_MODE="${JIUWENBOX_UDS_MODE:-}"
SAVE_LOGS_DIR="${JIUWENBOX_SAVE_LOGS_DIR:-}"

STOP_TIMEOUT_SECONDS=15
READY_TIMEOUT_SECONDS="${JIUWENBOX_READY_TIMEOUT:-15}"
READY_POLL_INTERVAL_SECONDS="${JIUWENBOX_READY_POLL_INTERVAL:-0.5}"
PGREP_PATTERN='[j]iuwenbox(-server|\.server\.launcher)'

# ===== systemd 模式常量 =====
JIUWENBOX_SVC="jiuwenbox"
JIUWENBOX_UNIT="/etc/systemd/system/${JIUWENBOX_SVC}.service"
JIUWENBOX_DROPIN_DIR="/etc/systemd/system/${JIUWENBOX_SVC}.service.d"
JIUWENBOX_DROPIN="${JIUWENBOX_DROPIN_DIR}/env.conf"
# systemd 托管会随机器重启拉起，而 RUN_DIR 默认在 /tmp（重启即清空），
# 故 policy 另存到持久目录，供开机自启动读取。
JIUWENBOX_STATE_DIR="${JIUWENBOX_STATE_DIR:-/var/lib/jiuwenbox}"

# ===== 日志 =====
info()    { echo -e "\033[36m=== $* ===\033[0m"; }
success() { echo -e "\033[32m✅ $*\033[0m"; }
warning() { echo -e "\033[33m⚠️  $*\033[0m"; }
error()   { echo -e "\033[31m❌ $*\033[0m"; exit 1; }

print_help() {
  cat <<EOF
Usage: ./$(basename "$0") <COMMAND> [OPTIONS]

Commands:
  up        在目标主机启动 jiuwenbox（每台各一份）
  down      在目标主机停止 jiuwenbox
  restart   先 down 再 up
  install   安装 jiuwenbox
  uninstall 卸载 jiuwenbox

Options:
  --hosts HOSTS   逗号分隔 IP；不指定则本机 IP
  --python PATH   Python 解释器（默认 python3）
  -h, --help      显示帮助

Environment:
  JIUWENBOX_RUN_DIR / JIUWENBOX_LISTEN / JIUWENBOX_READY_TIMEOUT
  JIUWENBOX_UDS_MODE / JIUWENBOX_SAVE_LOGS_DIR / JIUWENBOX_LOG_LEVEL

Notes:
  有 systemd 时生成 jiuwenbox.service（Restart=on-failure, RestartSec=3）并 enable；
  无 systemd 时回退 nohup（被 kill 后不会自动拉起）。

Examples:
  ./$(basename "$0") up --hosts 192.168.1.1,192.168.1.2
  ./$(basename "$0") down --hosts 192.168.1.1
  sudo ./$(basename "$0") --python python3.11 up
EOF
  exit 0
}

# ===== SSH =====
is_local_host() {
  local host="$1"
  if [ "${host}" = "127.0.0.1" ] || [ "${host}" = "localhost" ]; then
    return 0
  fi
  local local_ips
  local_ips=$(hostname -I 2>/dev/null || echo "")
  for ip in ${local_ips}; do
    [ "${host}" = "${ip}" ] && return 0
  done
  return 1
}

get_local_ip() {
  local local_ips ip
  local_ips=$(hostname -I 2>/dev/null || echo "")
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
    # shellcheck disable=SC2086
    ssh ${SSH_OPTS} "root@${host}" "$*"
  fi
}

jiuwenbox_check_ssh() {
  local host="$1"
  is_local_host "${host}" && return 0
  # shellcheck disable=SC2086
  ssh ${SSH_OPTS} "root@${host}" "echo ok" >/dev/null 2>&1
}

sync_remote_stage() {
  local host="$1"
  local remote_dir="${REMOTE_STAGE}/jiuwenbox"
  info "Syncing jiuwenbox scripts to ${host}:${remote_dir}"
  exec_on_host "${host}" "mkdir -p '${remote_dir}'"
  # shellcheck disable=SC2086
  scp ${SSH_OPTS} \
    "${SCRIPT_DIR}/jiuwenbox_deploy.sh" \
    "${POLICY_TEMPLATE}" \
    "root@${host}:${remote_dir}/" >/dev/null
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      exec sudo -E "$0" "$@"
    fi
    error "root privileges required; re-run with sudo"
  fi
}

python_bin() {
  echo "${PYTHON_CONFIG:-python3}"
}

# ===== 本机进程 / UDS =====
is_running_pid() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

find_server_pids() {
  command -v pgrep >/dev/null 2>&1 || return 0
  pgrep -f "$PGREP_PATTERN" 2>/dev/null || true
}

find_server_pid() {
  find_server_pids | head -n 1 || true
}

parse_listen_uri() {
  local uri="$1"
  LISTEN_MODE=""
  LISTEN_SOCKET_PATH=""
  case "$uri" in
    http://*) LISTEN_MODE="http" ;;
    unix:///*)
      LISTEN_MODE="uds"
      LISTEN_SOCKET_PATH="${uri#unix://}"
      ;;
    *) error "JIUWENBOX_LISTEN must start with http:// or unix:///, got '$uri'" ;;
  esac
}

remove_stale_uds_socket() {
  parse_listen_uri "$LISTEN_URI"
  if [[ "$LISTEN_MODE" = "uds" && -n "${LISTEN_SOCKET_PATH:-}" ]]; then
    if [[ -S "$LISTEN_SOCKET_PATH" || -e "$LISTEN_SOCKET_PATH" ]] \
      && ! is_running_pid "$(find_server_pid || true)"; then
      rm -f "$LISTEN_SOCKET_PATH"
    fi
  fi
}

# ===== policy / 前置检查 =====
resolve_extensions_dir() {
  local py pip_cmd location ext_dir
  py="$(python_bin)"
  pip_cmd="${py} -m pip"
  location="$(${pip_cmd} show jiuwenswarm 2>/dev/null | awk '/^Location:/{print $2}')" || true
  [ -n "${location}" ] || error "Cannot resolve jiuwenswarm via '${pip_cmd} show jiuwenswarm'. Is it installed?"
  ext_dir="${location}/jiuwenswarm/extensions"
  [ -d "${ext_dir}" ] || warning "extensions directory not found: ${ext_dir} (binding anyway)"
  echo "${ext_dir}"
}

# Candidate host binds for generate_policy. Order is mount order (bwrap later
# overrides earlier): parent dirs before children, all ro entries before rw.
POLICY_RO_PATHS=(/bin /sbin /usr /lib /lib64 /etc /opt)
POLICY_RW_PATHS=(/tmp)

generate_policy() {
  local ext_dir="$1" out_file path
  local ro_lines="" bind_lines="" mounted="" skipped=""
  mkdir -p "${RUN_DIR}"
  out_file="${RUN_DIR}/jiuwenbox-policy.yaml"
  [ -f "${POLICY_TEMPLATE}" ] || error "policy template not found: ${POLICY_TEMPLATE}"

  for path in "${POLICY_RO_PATHS[@]}"; do
    if [[ -e "${path}" ]]; then
      ro_lines+="    - \"${path}\""$'\n'
      bind_lines+="    - host_path: \"${path}\""$'\n'
      bind_lines+="      sandbox_path: \"${path}\""$'\n'
      bind_lines+="      mode: \"ro\""$'\n'
      info "policy mount: ${path} (ro)" >&2
      mounted+="${path}:ro "
    else
      warning "skip missing host path: ${path}" >&2
      skipped+="${path} "
    fi
  done
  for path in "${POLICY_RW_PATHS[@]}"; do
    if [[ -e "${path}" ]]; then
      bind_lines+="    - host_path: \"${path}\""$'\n'
      bind_lines+="      sandbox_path: \"${path}\""$'\n'
      bind_lines+="      mode: \"rw\""$'\n'
      info "policy mount: ${path} (rw)" >&2
      mounted+="${path}:rw "
    else
      warning "skip missing host path: ${path}" >&2
      skipped+="${path} "
    fi
  done
  info "policy mounts: ${mounted:-none}${skipped:+; skipped: ${skipped}}" >&2

  while IFS= read -r line || [[ -n "${line}" ]]; do
    case "${line}" in
      __DYNAMIC_READ_ONLY__)  printf '%s' "${ro_lines}" ;;
      __DYNAMIC_BIND_MOUNTS__) printf '%s' "${bind_lines}" ;;
      *) printf '%s\n' "${line//__JIUWENSWARM_EXTENSIONS_DIR__/${ext_dir}}" ;;
    esac
  done <"${POLICY_TEMPLATE}" >"${out_file}"
  echo "${out_file}"
}

policy_needs_iptables() {
  local policy="$1"
  [ -n "$policy" ] && [ -f "$policy" ] || return 0
  if grep -Eq '^[[:space:]]*mode:[[:space:]]*host[[:space:]]*$' "$policy"; then
    return 1
  fi
  return 0
}

check_iptables_backend() {
  local table="${1:-filter}" binary stderr_out failures=""
  local -a probe_args
  if [[ "$table" == "nat" ]]; then
    probe_args=(-t nat -L POSTROUTING -n)
  else
    probe_args=(-L OUTPUT -n)
  fi
  for binary in iptables iptables-nft iptables-legacy; do
    command -v "$binary" >/dev/null 2>&1 || continue
    if "$binary" "${probe_args[@]}" >/dev/null 2>&1; then
      return 0
    fi
    stderr_out="$("$binary" "${probe_args[@]}" 2>&1 | tail -n 1 || true)"
    failures="${failures}  ${binary}: ${stderr_out}"$'\n'
  done
  error "No working IPv4 iptables ${table} backend.${failures}Try: sudo modprobe ip_tables iptable_filter iptable_nat nf_nat"
}

check_prerequisites() {
  local py missing=() cmd
  py="$(python_bin)"
  command -v "$py" >/dev/null 2>&1 || error "python interpreter not found: $py"
  command -v jiuwenbox-server >/dev/null 2>&1 \
    || error "jiuwenbox-server not found in PATH; install jiuwenswarm first"
  command -v jiuwenbox >/dev/null 2>&1 \
    || error "jiuwenbox CLI not found in PATH; install jiuwenswarm first"
  for cmd in bwrap ip; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
  done
  if policy_needs_iptables "${POLICY_ABS:-}"; then
    if ! command -v iptables >/dev/null 2>&1 \
      && ! command -v iptables-nft >/dev/null 2>&1 \
      && ! command -v iptables-legacy >/dev/null 2>&1; then
      missing+=("iptables")
    fi
  fi
  ((${#missing[@]} == 0)) || error "missing required commands: ${missing[*]}"
  if policy_needs_iptables "${POLICY_ABS:-}"; then
    check_iptables_backend filter
    check_iptables_backend nat
  fi
  if ! "$py" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    error "python >= 3.11 required at $py"
  fi
}

probe_server_api() {
  jiuwenbox --base-url "$1" --timeout 2 sandbox ls >/dev/null 2>&1
}

wait_server_ready() {
  local base_url="$1" pid="${2:-}" restarts=""
  local deadline=$((SECONDS + READY_TIMEOUT_SECONDS))
  info "Waiting for jiuwenbox API ready (base-url=${base_url}, timeout=${READY_TIMEOUT_SECONDS}s)..."
  while (( SECONDS < deadline )); do
    if _jiuwenbox_has_systemd && [ -f "${JIUWENBOX_UNIT}" ]; then
      # 崩溃后 systemd 会进入 auto-restart，此时 is-failed 尚不成立（要等触发 start limit），
      # 故用 NRestarts>0 提前判定启动失败，避免白等整个 ready 超时。
      if systemctl is-failed --quiet "${JIUWENBOX_SVC}" 2>/dev/null; then
        echo "error: systemd unit ${JIUWENBOX_SVC} failed; see: journalctl -u ${JIUWENBOX_SVC}" >&2
        return 1
      fi
      restarts="$(systemctl show -p NRestarts --value "${JIUWENBOX_SVC}" 2>/dev/null || echo 0)"
      if [[ "${restarts}" =~ ^[0-9]+$ ]] && (( restarts > 0 )); then
        echo "error: ${JIUWENBOX_SVC} crashed and was restarted ${restarts} time(s) before becoming ready" >&2
        return 1
      fi
    elif [[ -n "${pid}" && "${pid}" != "0" ]] && ! is_running_pid "${pid}"; then
      echo "error: jiuwenbox process (pid ${pid}) exited before becoming ready" >&2
      return 1
    fi
    if probe_server_api "${base_url}"; then
      success "jiuwenbox API is ready"
      return 0
    fi
    sleep "${READY_POLL_INTERVAL_SECONDS}"
  done
  echo "error: jiuwenbox API not ready within ${READY_TIMEOUT_SECONDS}s" >&2
  return 1
}

# ===== systemd 托管 =====
_jiuwenbox_has_systemd() {
  command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]
}

# 生成 unit + drop-in 并 enable --now。调用方已完成 policy / 目录 / 前置检查。
_jiuwenbox_start_systemd() {
  local server_bin py py_bindir py_libdir log_level exec_start pid
  local mkdir_bin pre_dirs systemd_ver log_lines
  server_bin="$(command -v jiuwenbox-server)" || error "jiuwenbox-server not found"
  py="$(python_bin)"
  py_bindir="$(dirname "$(command -v "${py}")")"
  py_libdir="${py_bindir}/lib"
  log_level="${JIUWENBOX_LOG_LEVEL:-info}"
  exec_start="${server_bin} --log-level ${log_level}"
  [[ -n "${SAVE_LOGS_DIR:-}" ]] && exec_start="${exec_start} --save-logs ${SAVE_LOGS_DIR}"

  # 开机自启动时 /tmp、/run 已被清空，需在 ExecStart 前重建日志目录与 UDS 目录
  mkdir_bin="$(command -v mkdir)" || error "mkdir not found"
  pre_dirs="${RUN_DIR}"
  if [[ "${LISTEN_MODE:-}" = "uds" && -n "${LISTEN_SOCKET_PATH:-}" ]]; then
    pre_dirs="${pre_dirs} $(dirname "${LISTEN_SOCKET_PATH}")"
  fi
  [[ -n "${SAVE_LOGS_DIR:-}" ]] && pre_dirs="${pre_dirs} ${SAVE_LOGS_DIR}"

  # StandardOutput=append: 需 systemd >= 240；更老的版本只落 journal
  systemd_ver="$(systemctl --version 2>/dev/null | awk 'NR==1{print $2}')"
  if [[ "${systemd_ver}" =~ ^[0-9]+$ ]] && (( systemd_ver >= 240 )); then
    log_lines="StandardOutput=append:${LOG_FILE}"$'\n'"StandardError=append:${LOG_FILE}"
  else
    log_lines="StandardOutput=journal"$'\n'"StandardError=journal"
    info "systemd ${systemd_ver:-unknown} < 240, logs go to journal (journalctl -u ${JIUWENBOX_SVC})"
  fi

  info "systemd detected, generating unit ${JIUWENBOX_SVC}..."
  cat > "${JIUWENBOX_UNIT}" <<EOF
[Unit]
Description=Jiuwenbox Sandbox Service
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
ExecStartPre=${mkdir_bin} -p ${pre_dirs}
ExecStart=${exec_start}
Restart=on-failure
RestartSec=3
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=${STOP_TIMEOUT_SECONDS}s
${log_lines}

[Install]
WantedBy=multi-user.target
EOF

  mkdir -p "${JIUWENBOX_DROPIN_DIR}"
  cat > "${JIUWENBOX_DROPIN}" <<EOF
[Service]
Environment=PATH=${py_bindir}:${PATH}
Environment=LD_LIBRARY_PATH=${py_libdir}:${LD_LIBRARY_PATH:-}
Environment=JIUWENBOX_LISTEN=${LISTEN_URI}
Environment=JIUWENBOX_POLICY_PATH=${POLICY_ABS}
EOF
  if [[ -n "${UDS_MODE:-}" ]]; then
    echo "Environment=JIUWENBOX_UDS_MODE=${UDS_MODE}" >> "${JIUWENBOX_DROPIN}"
  fi
  if [[ -n "${SAVE_LOGS_DIR:-}" ]]; then
    echo "Environment=JIUWENBOX_SAVE_LOGS_DIR=${SAVE_LOGS_DIR}" >> "${JIUWENBOX_DROPIN}"
  fi

  systemctl daemon-reload
  systemctl reset-failed "${JIUWENBOX_SVC}" 2>/dev/null || true
  systemctl enable --now "${JIUWENBOX_SVC}" || error "Failed to start ${JIUWENBOX_SVC}"

  pid="$(systemctl show -p MainPID --value "${JIUWENBOX_SVC}" 2>/dev/null || true)"
  if ! wait_server_ready "${LISTEN_URI}" "${pid}"; then
    echo "error: server failed to become ready; see: journalctl -u ${JIUWENBOX_SVC} and ${LOG_FILE}" >&2
    journalctl -u "${JIUWENBOX_SVC}" -n 40 --no-pager >&2 || true
    tail -n 40 "$LOG_FILE" >&2 || true
    systemctl stop "${JIUWENBOX_SVC}" 2>/dev/null || true
    exit 1
  fi
  success "Started jiuwenbox (systemd: ${JIUWENBOX_SVC}, pid ${pid:-unknown})"
}

# ===== 本机启停核心（仅函数，不对外暴露；由 up/down 按 host 调用） =====
stop_server_processes() {
  local pids pid waited=0 remaining=""
  pids="$(find_server_pids)"
  if [[ -z "$pids" ]]; then
    remove_stale_uds_socket
    echo "jiuwenbox is not running"
    return 0
  fi
  echo "Stopping jiuwenbox process(es): ${pids//$'\n'/ }..."
  for pid in $pids; do
    kill -TERM "$pid" 2>/dev/null || true
  done
  while (( waited < STOP_TIMEOUT_SECONDS )); do
    remaining="$(find_server_pids)"
    [[ -z "$remaining" ]] && break
    sleep 1
    waited=$((waited + 1))
  done
  remaining="$(find_server_pids)"
  if [[ -n "$remaining" ]]; then
    echo "Process(es) did not exit; sending SIGKILL: ${remaining//$'\n'/ }"
    for pid in $remaining; do
      kill -KILL "$pid" 2>/dev/null || true
    done
    sleep 1
  fi
  remove_stale_uds_socket
  echo "Stopped jiuwenbox"
}

# 本机是否在跑（供 check_existing；远端用 SSH pgrep）
jiuwenbox_status_on_host() {
  local host="$1"
  if is_local_host "${host}"; then
    local pids
    # 崩溃重启间隙进程可能暂时不在，故 systemd 模式下先看 unit 状态
    if _jiuwenbox_has_systemd && systemctl is-active --quiet "${JIUWENBOX_SVC}" 2>/dev/null; then
      echo "jiuwenbox is running (systemd: ${JIUWENBOX_SVC})"
      return 0
    fi
    pids="$(find_server_pids)"
    if [[ -n "$pids" ]]; then
      echo "jiuwenbox is running (pid(s): ${pids//$'\n'/ })"
      return 0
    fi
    echo "jiuwenbox is not running"
    return 1
  fi
  if exec_on_host "${host}" \
    "systemctl is-active --quiet ${JIUWENBOX_SVC} 2>/dev/null || pgrep -f '${PGREP_PATTERN}' >/dev/null 2>&1"; then
    echo "jiuwenbox is running on ${host}"
    return 0
  fi
  echo "jiuwenbox is not running on ${host}"
  return 1
}

# 在当前机器启动一份 jiuwenbox（调用方已保证 root）
start_on_this_host() {
  local existing_pid ext_dir policy_file py log_level pid
  local -a start_env server_args

  existing_pid="$(find_server_pid || true)"
  if [[ -n "$existing_pid" ]]; then
    error "Existing jiuwenbox detected (pid ${existing_pid}). Please run 'down' first, then retry 'up'."
  fi

  ext_dir="$(resolve_extensions_dir)"
  info "jiuwenswarm extensions dir: ${ext_dir}"
  policy_file="$(generate_policy "${ext_dir}")"
  info "generated jiuwenbox policy: ${policy_file}"
  POLICY_ABS="${policy_file}"

  # systemd 托管含开机自启动，而 RUN_DIR 默认在 /tmp（重启即清空），
  # policy 留在那里会导致重启后服务起不来，故另存一份到持久目录。
  if _jiuwenbox_has_systemd; then
    mkdir -p "${JIUWENBOX_STATE_DIR}"
    cp -f "${policy_file}" "${JIUWENBOX_STATE_DIR}/jiuwenbox-policy.yaml"
    POLICY_ABS="${JIUWENBOX_STATE_DIR}/jiuwenbox-policy.yaml"
    info "persisted policy for systemd: ${POLICY_ABS}"
  fi

  check_prerequisites
  parse_listen_uri "$LISTEN_URI"
  remove_stale_uds_socket
  mkdir -p "$RUN_DIR"
  if [[ "$LISTEN_MODE" = "uds" ]]; then
    mkdir -p "$(dirname "$LISTEN_SOCKET_PATH")"
  fi
  if [[ -n "${SAVE_LOGS_DIR:-}" ]]; then
    mkdir -p "$SAVE_LOGS_DIR"
    SAVE_LOGS_DIR="$(realpath "$SAVE_LOGS_DIR")"
  fi

  if _jiuwenbox_has_systemd; then
    _jiuwenbox_start_systemd
    return
  fi

  info "systemd not available, using nohup mode..."
  py="$(python_bin)"
  log_level="${JIUWENBOX_LOG_LEVEL:-info}"
  start_env=("JIUWENBOX_LISTEN=$LISTEN_URI" "JIUWENBOX_POLICY_PATH=$POLICY_ABS")
  [[ -n "${UDS_MODE:-}" ]] && start_env+=("JIUWENBOX_UDS_MODE=$UDS_MODE")
  [[ -n "${SAVE_LOGS_DIR:-}" ]] && start_env+=("JIUWENBOX_SAVE_LOGS_DIR=$SAVE_LOGS_DIR")
  server_args=(--log-level "$log_level")
  [[ -n "${SAVE_LOGS_DIR:-}" ]] && server_args+=(--save-logs "$SAVE_LOGS_DIR")

  info "Starting jiuwenbox-server (listen=${LISTEN_URI}, policy=${POLICY_ABS}, log=${LOG_FILE})"
  nohup env "${start_env[@]}" jiuwenbox-server "${server_args[@]}" >>"$LOG_FILE" 2>&1 &
  pid=$!

  if ! wait_server_ready "${LISTEN_URI}" "${pid}"; then
    echo "error: server failed to become ready; see $LOG_FILE" >&2
    tail -n 40 "$LOG_FILE" >&2 || true
    stop_server_processes >/dev/null || true
    exit 1
  fi

  success "Started jiuwenbox (pid $pid)"
}

stop_on_this_host() {
  if _jiuwenbox_has_systemd && [ -f "${JIUWENBOX_UNIT}" ]; then
    if systemctl stop "${JIUWENBOX_SVC}" 2>/dev/null; then
      success "jiuwenbox stopped (systemd: ${JIUWENBOX_SVC})"
    else
      warning "jiuwenbox systemd unit not running"
    fi
  fi
  # 兜底清理 nohup 残留（例如此前无 systemd 拉起的进程）
  if [[ -n "$(find_server_pids)" ]]; then
    stop_server_processes
  else
    remove_stale_uds_socket
  fi
}

uninstall_on_this_host() {
  if _jiuwenbox_has_systemd; then
    systemctl disable --now "${JIUWENBOX_SVC}" 2>/dev/null || true
    rm -rf "${JIUWENBOX_UNIT}" "${JIUWENBOX_DROPIN_DIR}"
    systemctl daemon-reload 2>/dev/null || true
    systemctl reset-failed "${JIUWENBOX_SVC}" 2>/dev/null || true
    rm -rf "${JIUWENBOX_STATE_DIR}"
    success "jiuwenbox systemd unit removed"
  fi
  stop_server_processes >/dev/null || true
}

# ===== 多机调度：up/down/uninstall 内区分本机 / 远端 =====
# 本机：直接 start/stop/uninstall_on_this_host
# 远端：scp 后执行同一套命令（不带 --hosts → 在对端对本机 IP 启停）
jiuwenbox_run_on_host() {
  local host="$1" sub="$2"
  if is_local_host "${host}"; then
    case "${sub}" in
      up)         start_on_this_host ;;
      down)       stop_on_this_host ;;
      uninstall)  uninstall_on_this_host ;;
      *)          error "unknown local sub: ${sub}" ;;
    esac
    return $?
  fi

  sync_remote_stage "${host}"
  local remote_script="${REMOTE_STAGE}/jiuwenbox/jiuwenbox_deploy.sh"
  local py
  py="$(python_bin)"
  case "${sub}" in
    up|down|uninstall)
      # 对端跑公开命令；默认 CLUSTER_HOSTS=对端本机 IP，只会走本机分支
      exec_on_host "${host}" \
        "JIUWENBOX_RUN_DIR='${RUN_DIR}' JIUWENBOX_LISTEN='${LISTEN_URI}' bash '${remote_script}' --python '${py}' ${sub}"
      ;;
    *)
      error "unknown host sub: ${sub}"
      ;;
  esac
}

# 对齐 yuanrong yr_check_existing：已存在则报错，不自动清理
jiuwenbox_check_existing() {
  local host="$1" status_out=""
  info "Checking for existing jiuwenbox on ${host}..."
  if status_out="$(jiuwenbox_status_on_host "${host}" 2>&1)"; then
    error "Existing jiuwenbox detected on ${host}: ${status_out} Please run 'down' first, then retry 'up'."
  fi
  info "No existing jiuwenbox on ${host}"
}

_require_root_if_local_in_hosts() {
  local hosts_str="$1" cluster_cmd="$2" host
  IFS=',' read -ra _rh <<< "${hosts_str}"
  for host in "${_rh[@]}"; do
    host="$(echo "${host}" | tr -d '[:space:]')"
    [ -z "${host}" ] && continue
    if is_local_host "${host}"; then
      require_root "$0" --python "$(python_bin)" "${cluster_cmd}" --hosts "${hosts_str}"
      return 0
    fi
  done
}

deploy_jiuwenbox_up() {
  local hosts_str="${CLUSTER_HOSTS}" host
  local jiuwenbox_up_phase=0

  IFS=',' read -ra JIUWENBOX_HOST_LIST <<< "${hosts_str}"

  trap '
    if [ "${jiuwenbox_up_phase:-0}" = "1" ]; then
      warning "deploy_jiuwenbox_up failed during startup, cleaning up jiuwenbox on all hosts..."
      for _h in "${JIUWENBOX_HOST_LIST[@]}"; do
        _h="$(echo "${_h}" | tr -d "[:space:]")"
        [ -z "${_h}" ] && continue
        jiuwenbox_run_on_host "${_h}" down >/dev/null 2>&1 || true
      done
    fi
  ' EXIT

  _require_root_if_local_in_hosts "${hosts_str}" up

  info "Deploying jiuwenbox"
  info "Hosts: ${hosts_str}"
  info "Python: $(python_bin)"

  info "Checking connectivity..."
  for host in "${JIUWENBOX_HOST_LIST[@]}"; do
    host="$(echo "${host}" | tr -d '[:space:]')"
    [ -z "${host}" ] && continue
    if is_local_host "${host}"; then
      success "${host} is local host, skip SSH check"
    elif jiuwenbox_check_ssh "${host}"; then
      success "SSH to ${host} OK"
    else
      error "SSH to ${host} failed! Configure SSH key authentication first."
    fi
  done

  for host in "${JIUWENBOX_HOST_LIST[@]}"; do
    host="$(echo "${host}" | tr -d '[:space:]')"
    [ -z "${host}" ] && continue
    jiuwenbox_check_existing "${host}"
  done

  jiuwenbox_up_phase=1
  for host in "${JIUWENBOX_HOST_LIST[@]}"; do
    host="$(echo "${host}" | tr -d '[:space:]')"
    [ -z "${host}" ] && continue
    info "Starting jiuwenbox on ${host}..."
    jiuwenbox_run_on_host "${host}" up
    success "jiuwenbox started on ${host}"
  done

  jiuwenbox_up_phase=2
  trap - EXIT
  success "jiuwenbox deployment completed!"
  echo "  Hosts: ${hosts_str}"
  echo "  Stop:  ./$(basename "$0") down --hosts ${hosts_str}"
}

deploy_jiuwenbox_down() {
  local hosts_str="${CLUSTER_HOSTS}" host
  IFS=',' read -ra JIUWENBOX_HOST_LIST <<< "${hosts_str}"
  _require_root_if_local_in_hosts "${hosts_str}" down

  info "Stopping jiuwenbox on hosts: ${hosts_str}"
  for host in "${JIUWENBOX_HOST_LIST[@]}"; do
    host="$(echo "${host}" | tr -d '[:space:]')"
    [ -z "${host}" ] && continue
    if ! is_local_host "${host}" && ! jiuwenbox_check_ssh "${host}"; then
      warning "SSH to ${host} failed, skip"
      continue
    fi
    info "Stopping jiuwenbox on ${host}..."
    jiuwenbox_run_on_host "${host}" down || warning "Failed to stop on ${host} (may not be running)"
    success "jiuwenbox stopped on ${host}"
  done
}

deploy_jiuwenbox_restart() {
  deploy_jiuwenbox_down
  deploy_jiuwenbox_up
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
        CLUSTER_HOSTS="${args[$((i+1))]:-}"
        [ -n "${CLUSTER_HOSTS}" ] || error "--hosts requires a comma-separated host list"
        i=$((i+2))
        ;;
      --hosts=*)
        CLUSTER_HOSTS="${args[$i]#--hosts=}"
        i=$((i+1))
        ;;
      --python)
        PYTHON_CONFIG="${args[$((i+1))]:-}"
        [ -n "${PYTHON_CONFIG}" ] || error "--python requires a path"
        i=$((i+2))
        ;;
      --python=*)
        PYTHON_CONFIG="${args[$i]#--python=}"
        i=$((i+1))
        ;;
      -h|--help|help)
        print_help
        ;;
      *)
        error "Invalid Args: ${args[$i]}"
        ;;
    esac
  done

  [ -n "${CMD:-}" ] || print_help

  if [ -z "${CLUSTER_HOSTS:-}" ]; then
    CLUSTER_HOSTS="$(get_local_ip)"
    warning "CLUSTER_HOSTS not specified, using local IP: ${CLUSTER_HOSTS}"
  fi
}

deploy_jiuwenbox_install() {
  info "Installing jiuwenbox"
  info "Hosts: ${CLUSTER_HOSTS}"
  info "Python: $(python_bin)"
  if _jiuwenbox_has_systemd; then
    info "systemd detected; jiuwenbox will be managed by systemd on up (Restart=on-failure)"
  else
    info "systemd not available; jiuwenbox will use nohup on up"
  fi
}

deploy_jiuwenbox_uninstall() {
  local hosts_str="${CLUSTER_HOSTS}" host
  IFS=',' read -ra JIUWENBOX_HOST_LIST <<< "${hosts_str}"
  _require_root_if_local_in_hosts "${hosts_str}" uninstall

  info "Uninstalling jiuwenbox on hosts: ${hosts_str}"
  for host in "${JIUWENBOX_HOST_LIST[@]}"; do
    host="$(echo "${host}" | tr -d '[:space:]')"
    [ -z "${host}" ] && continue
    if ! is_local_host "${host}" && ! jiuwenbox_check_ssh "${host}"; then
      warning "SSH to ${host} failed, skip"
      continue
    fi
    info "Uninstalling jiuwenbox on ${host}..."
    jiuwenbox_run_on_host "${host}" uninstall || warning "Failed to uninstall on ${host}"
    success "jiuwenbox uninstalled on ${host}"
  done
}

main() {
  parse_args "$@"
  case "${CMD}" in
    up)        deploy_jiuwenbox_up ;;
    down)      deploy_jiuwenbox_down ;;
    restart)   deploy_jiuwenbox_restart ;;
    install)   deploy_jiuwenbox_install ;;
    uninstall) deploy_jiuwenbox_uninstall ;;
    *)         error "Unknown command: ${CMD}" ;;
  esac
}

main "$@"
