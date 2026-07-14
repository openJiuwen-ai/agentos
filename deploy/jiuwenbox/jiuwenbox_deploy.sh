#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CALLER_CWD="$(pwd)"

VENV_DIR="$PROJECT_DIR/.venv"
RUN_DIR="$PROJECT_DIR/.run"
PID_FILE="$RUN_DIR/jiuwenbox.pid"
LOG_FILE="$RUN_DIR/jiuwenbox.log"
LAST_ENV_FILE="$RUN_DIR/last-start.env"
DEFAULT_LISTEN="unix:///run/jiuwenbox/jiuwenbox.sock"

PYTHON=""
SERVER_BIN=""
PYTHON_CONFIG=""

LISTEN_URI="${JIUWENBOX_LISTEN:-$DEFAULT_LISTEN}"
UDS_MODE="${JIUWENBOX_UDS_MODE:-}"
SAVE_LOGS_DIR="${JIUWENBOX_SAVE_LOGS_DIR:-}"

STOP_TIMEOUT_SECONDS=15
PGREP_PATTERN='[j]iuwenbox\.server\.launcher'

usage() {
  cat <<'EOF'
Usage: jiuwenbox_deploy.sh [--python PATH] <command> [options]

Commands:
  start [policy.yaml]     Start jiuwenbox-server in background (or --foreground)
  stop                    Stop the running server
  clean                   Stop server and remove ~/.jiuwenbox/ and .run/

Global options:
  --python PATH           Python interpreter (default: .venv/bin/python3, else python3)
                          jiuwenbox-server is resolved from the same bin/ directory

Start options:
  --save-logs DIR         Persist per-sandbox audit JSONL under DIR
                          (equivalent to JIUWENBOX_SAVE_LOGS_DIR)
  --foreground            Run in foreground (start only; no pid file)
  --python PATH           Same as the global option (may appear after start)

Environment (same names as run_docker.sh / launcher):
  JIUWENBOX_LISTEN        Listen URI (default unix:///run/jiuwenbox/jiuwenbox.sock)
  JIUWENBOX_POLICY_PATH   Policy file absolute path (set by script when given)
  JIUWENBOX_UDS_MODE      UDS socket mode (e.g. 0666)
  JIUWENBOX_SAVE_LOGS_DIR Audit log directory
  JIUWENBOX_LOG_LEVEL     uvicorn log level (default info)

Examples:
  sudo ./jiuwenbox_deploy.sh start
  sudo ./jiuwenbox_deploy.sh --python .venv/bin/python3 start
  sudo ./jiuwenbox_deploy.sh start --python .venv/bin/python3 ./default-policy.yaml
  sudo ./jiuwenbox_deploy.sh --python .venv/bin/python3 clean
  sudo ./jiuwenbox_deploy.sh stop
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      exec sudo -E "$0" "$@"
    fi
    die "root privileges required; re-run with sudo"
  fi
}

is_running_pid() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

read_pid() {
  if [[ -f "$PID_FILE" ]]; then
    tr -d '[:space:]' <"$PID_FILE"
    return 0
  fi
  return 1
}

find_server_pid() {
  local pid=""
  if pid="$(read_pid 2>/dev/null || true)" && is_running_pid "$pid"; then
    echo "$pid"
    return 0
  fi
  if command -v pgrep >/dev/null 2>&1; then
    pgrep -f "$PGREP_PATTERN" 2>/dev/null | head -n 1 || true
  fi
}

parse_listen_uri() {
  local uri="$1"
  LISTEN_MODE=""
  LISTEN_SOCKET_PATH=""
  case "$uri" in
    http://*)
      LISTEN_MODE="http"
      ;;
    unix:///*)
      LISTEN_MODE="uds"
      LISTEN_SOCKET_PATH="${uri#unix://}"
      ;;
    *)
      die "JIUWENBOX_LISTEN must start with http:// or unix:///, got '$uri'"
      ;;
  esac
}

resolve_policy_path() {
  local policy="$1"
  local resolved=""

  if [[ -z "$policy" ]]; then
    POLICY_ABS=""
    return 0
  fi

  if [[ "$policy" = /* && -f "$policy" ]]; then
    resolved="$(realpath "$policy")"
  elif [[ -f "$CALLER_CWD/$policy" ]]; then
    resolved="$(realpath "$CALLER_CWD/$policy")"
  elif [[ -f "$PROJECT_DIR/$policy" ]]; then
    resolved="$(realpath "$PROJECT_DIR/$policy")"
  else
    die "policy config not found: $policy"
  fi

  POLICY_ABS="$resolved"
}

uds_socket_parent() {
  if [[ "$LISTEN_MODE" = "uds" && -n "${LISTEN_SOCKET_PATH:-}" ]]; then
    dirname "$LISTEN_SOCKET_PATH"
  fi
}

remove_stale_uds_socket() {
  parse_listen_uri "$LISTEN_URI"
  if [[ "$LISTEN_MODE" = "uds" && -n "${LISTEN_SOCKET_PATH:-}" ]]; then
    if [[ -S "$LISTEN_SOCKET_PATH" || -e "$LISTEN_SOCKET_PATH" ]] && ! is_running_pid "$(find_server_pid || true)"; then
      rm -f "$LISTEN_SOCKET_PATH"
    fi
  fi
}

set_python_config() {
  local candidate="$1"
  if [[ -z "$candidate" ]]; then
    die "--python requires a non-empty path"
  fi
  PYTHON_CONFIG="$candidate"
}

# Remove a leading --python option from "$@" when present.
# Returns 0 and leaves the remaining args in REPLY when consumed.
consume_python_option() {
  REPLY=("$@")
  if ((${#REPLY[@]} == 0)); then
    return 1
  fi

  case "${REPLY[0]}" in
    --python=*)
      set_python_config "${REPLY[0]#--python=}"
      REPLY=("${REPLY[@]:1}")
      return 0
      ;;
    --python)
      if ((${#REPLY[@]} < 2)); then
        die "--python requires a path"
      fi
      set_python_config "${REPLY[1]}"
      REPLY=("${REPLY[@]:2}")
      return 0
      ;;
  esac
  return 1
}

resolve_python_and_server_bin() {
  local candidate="${PYTHON_CONFIG:-}"

  if [[ -z "$candidate" && -f "$LAST_ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$LAST_ENV_FILE"
    candidate="${PYTHON_PATH:-}"
  fi

  if [[ -z "$candidate" ]]; then
    if [[ -x "$VENV_DIR/bin/python3" ]]; then
      candidate="$VENV_DIR/bin/python3"
    else
      candidate="python3"
    fi
  fi

  if [[ "$candidate" == */* ]]; then
    if [[ ! -e "$candidate" ]]; then
      die "python interpreter not found: $candidate"
    fi
    PYTHON="$(realpath "$candidate")"
  elif command -v "$candidate" >/dev/null 2>&1; then
    PYTHON="$(command -v "$candidate")"
  else
    die "python interpreter not found: $candidate"
  fi

  if [[ ! -x "$PYTHON" ]]; then
    die "python interpreter is not executable: $PYTHON"
  fi

  SERVER_BIN="$(dirname "$PYTHON")/jiuwenbox-server"
}

check_prerequisites() {
  resolve_python_and_server_bin

  local missing=()
  for cmd in bwrap ip; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      missing+=("$cmd")
    fi
  done
  if ! command -v iptables >/dev/null 2>&1 \
    && ! command -v iptables-nft >/dev/null 2>&1 \
    && ! command -v iptables-legacy >/dev/null 2>&1; then
    missing+=("iptables (or iptables-nft / iptables-legacy)")
  fi
  if ((${#missing[@]} > 0)); then
    die "missing required commands: ${missing[*]}"
  fi

  local pyver
  pyver="$("$PYTHON" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')"
  if "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    :
  else
    die "python >= 3.11 required at $PYTHON, found $pyver"
  fi
}

write_last_start_env() {
  mkdir -p "$RUN_DIR"
  {
    echo "LISTEN_URI=$LISTEN_URI"
    echo "PYTHON_PATH=$PYTHON"
    if [[ -n "${POLICY_ABS:-}" ]]; then
      echo "POLICY_ABS=$POLICY_ABS"
    fi
    if [[ -n "${SAVE_LOGS_DIR:-}" ]]; then
      echo "SAVE_LOGS_DIR=$SAVE_LOGS_DIR"
    fi
    if [[ -n "${UDS_MODE:-}" ]]; then
      echo "UDS_MODE=$UDS_MODE"
    fi
    echo "LOG_LEVEL=${JIUWENBOX_LOG_LEVEL:-info}"
  } >"$LAST_ENV_FILE"
}

parse_start_args() {
  local default_policy="${1:-}"
  shift || true

  POLICY_CONFIG=""
  SAVE_LOGS_CLI=""
  FOREGROUND=false

  while [[ $# -gt 0 ]]; do
    if consume_python_option "$@"; then
      set -- "${REPLY[@]}"
      continue
    fi

    case "$1" in
      --save-logs=*)
        SAVE_LOGS_CLI="${1#--save-logs=}"
        if [[ -z "$SAVE_LOGS_CLI" ]]; then
          die "--save-logs requires a non-empty directory path"
        fi
        shift
        ;;
      --save-logs)
        if [[ $# -lt 2 || "$2" == --* ]]; then
          die "--save-logs requires a directory path"
        fi
        SAVE_LOGS_CLI="$2"
        shift 2
        ;;
      --foreground)
        FOREGROUND=true
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      -*)
        die "unknown option for start: $1"
        ;;
      *)
        if [[ -z "$POLICY_CONFIG" ]]; then
          POLICY_CONFIG="$1"
          shift
        else
          die "unexpected argument: $1"
        fi
        ;;
    esac
  done

  if [[ -z "$POLICY_CONFIG" && -n "$default_policy" ]]; then
    POLICY_CONFIG="$default_policy"
  fi

  if [[ -n "$SAVE_LOGS_CLI" ]]; then
    SAVE_LOGS_DIR="$SAVE_LOGS_CLI"
  fi
}

build_start_env() {
  resolve_policy_path "${POLICY_CONFIG:-}"
  parse_listen_uri "$LISTEN_URI"

  if [[ "$LISTEN_MODE" = "uds" ]]; then
    mkdir -p "$(uds_socket_parent)"
  fi

  if [[ -n "${SAVE_LOGS_DIR:-}" ]]; then
    mkdir -p "$SAVE_LOGS_DIR"
    SAVE_LOGS_DIR="$(realpath "$SAVE_LOGS_DIR")"
  fi

  START_ENV=(
    "JIUWENBOX_LISTEN=$LISTEN_URI"
  )
  if [[ -n "${POLICY_ABS:-}" ]]; then
    START_ENV+=("JIUWENBOX_POLICY_PATH=$POLICY_ABS")
  fi
  if [[ -n "${UDS_MODE:-}" ]]; then
    START_ENV+=("JIUWENBOX_UDS_MODE=$UDS_MODE")
  fi
  if [[ -n "${SAVE_LOGS_DIR:-}" ]]; then
    START_ENV+=("JIUWENBOX_SAVE_LOGS_DIR=$SAVE_LOGS_DIR")
  fi
}

cmd_start() {
  local default_policy="${1:-}"
  shift || true
  parse_start_args "$default_policy" "$@"
  check_prerequisites

  if [[ ! -x "$SERVER_BIN" ]]; then
    die "jiuwenbox-server not found at $SERVER_BIN; install the package first (e.g. uv sync && uv pip install -e .)"
  fi

  local existing_pid
  existing_pid="$(find_server_pid || true)"
  if [[ -n "$existing_pid" ]]; then
    echo "jiuwenbox is already running (pid $existing_pid)"
    exit 0
  fi

  build_start_env
  remove_stale_uds_socket
  mkdir -p "$RUN_DIR"

  local log_level="${JIUWENBOX_LOG_LEVEL:-info}"
  local -a server_args=(--log-level "$log_level")
  if [[ -n "${SAVE_LOGS_DIR:-}" ]]; then
    server_args+=(--save-logs "$SAVE_LOGS_DIR")
  fi

  echo "Starting jiuwenbox server:"
  echo "  python:  $PYTHON"
  echo "  binary:  $SERVER_BIN"
  echo "  listen:  $LISTEN_URI"
  if [[ -n "${POLICY_ABS:-}" ]]; then
    echo "  policy:  $POLICY_ABS"
  else
    echo "  policy:  bundled default-policy.yaml (wheel)"
  fi
  if [[ -n "${SAVE_LOGS_DIR:-}" ]]; then
    echo "  save-logs: $SAVE_LOGS_DIR"
  fi
  echo "  log:     $LOG_FILE"

  if [[ "$FOREGROUND" = true ]]; then
    exec env "${START_ENV[@]}" "$SERVER_BIN" "${server_args[@]}"
  fi

  nohup env "${START_ENV[@]}" "$SERVER_BIN" "${server_args[@]}" >>"$LOG_FILE" 2>&1 &
  local pid=$!
  echo "$pid" >"$PID_FILE"
  write_last_start_env

  sleep 1
  if ! is_running_pid "$pid"; then
    echo "error: server failed to start; see $LOG_FILE" >&2
    tail -n 20 "$LOG_FILE" >&2 || true
    exit 1
  fi

  echo "Started jiuwenbox (pid $pid)"
}

cmd_stop() {
  local pid
  pid="$(find_server_pid || true)"

  if [[ -z "$pid" ]]; then
    echo "jiuwenbox is not running"
    rm -f "$PID_FILE"
    remove_stale_uds_socket
    exit 0
  fi

  echo "Stopping jiuwenbox (pid $pid)..."
  kill -TERM "$pid" 2>/dev/null || true

  local waited=0
  while is_running_pid "$pid" && (( waited < STOP_TIMEOUT_SECONDS )); do
    sleep 1
    waited=$((waited + 1))
  done

  if is_running_pid "$pid"; then
    echo "Process did not exit; sending SIGKILL"
    kill -KILL "$pid" 2>/dev/null || true
    sleep 1
  fi

  rm -f "$PID_FILE"
  remove_stale_uds_socket
  echo "Stopped jiuwenbox"
}

jiuwenbox_home_dir() {
  resolve_python_and_server_bin
  "$PYTHON" -c 'import os, pwd; print(pwd.getpwuid(os.geteuid()).pw_dir + "/.jiuwenbox")'
}

parse_clean_args() {
  while [[ $# -gt 0 ]]; do
    if consume_python_option "$@"; then
      set -- "${REPLY[@]}"
      continue
    fi

    case "$1" in
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "clean does not accept options (got: $1)"
        ;;
    esac
  done
}

cmd_clean() {
  parse_clean_args "$@"

  if [[ -f "$LAST_ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$LAST_ENV_FILE"
    if [[ -z "$PYTHON_CONFIG" ]]; then
      PYTHON_CONFIG="${PYTHON_PATH:-}"
    fi
    LISTEN_URI="${LISTEN_URI:-$DEFAULT_LISTEN}"
  fi

  cmd_stop || true
  remove_stale_uds_socket
  rm -rf "$RUN_DIR"

  local home_dir
  home_dir="$(jiuwenbox_home_dir)"
  rm -rf "$home_dir"
  echo "Removed $home_dir"
  echo "Removed $RUN_DIR"
  echo "Clean complete"
}

main() {
  if [[ $# -eq 0 ]]; then
    usage
    exit 1
  fi

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help|help)
        usage
        exit 0
        ;;
      --python=*)
        set_python_config "${1#--python=}"
        shift
        ;;
      --python)
        if [[ $# -lt 2 ]]; then
          die "--python requires a path"
        fi
        set_python_config "$2"
        shift 2
        ;;
      start|stop|clean)
        break
        ;;
      *)
        die "unknown option or command: $1 (run '$0 --help')"
        ;;
    esac
  done

  if [[ $# -eq 0 ]]; then
    usage
    exit 1
  fi

  local cmd="$1"
  shift

  case "$cmd" in
    start)
      require_root "$0" ${PYTHON_CONFIG:+--python "$PYTHON_CONFIG"} start "$@"
      cmd_start "" "$@"
      ;;
    stop)
      require_root "$0" stop "$@"
      cmd_stop "$@"
      ;;
    clean)
      require_root "$0" ${PYTHON_CONFIG:+--python "$PYTHON_CONFIG"} clean "$@"
      cmd_clean "$@"
      ;;
    *)
      die "unknown command: $cmd (run '$0 --help')"
      ;;
  esac
}

main "$@"
