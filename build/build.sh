#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_DIR="${PROJECT_ROOT}/build/dist"
DOWNLOAD_DIR="${BUILD_DIR}/downloads"
DEPLOY_DIR="${PROJECT_ROOT}/deploy"

# build parameters
BUILD_MODE="daily"
CP_TAG="cp311"
ARCH="$(uname -m)"
YUANRONG_RELEASE_VERSION="0.9.0"
JIUWENSWARM_RELEASE_VERSION="0.2.3"
JIUWENSWARM_RELEASE_GIT_TAG="release_0.2.3"
YUANRONG_DAILY_VERSION="9.9.9"
YR_SCHEDULE_TIME=""
YR_RELEASE_DOWNLOAD_BASE=""
DOWNLOAD_JOBS=3
REGISTRY_RELEASE_TAG="agentos-registry-prerelease-v0.2.1"
REGISTRY_WHL_VERSION="0.3.3"
RQLITE_VERSION="10.2.7"
# ./ build parameters

YUANRONG_DAILY_INDEX_URL="https://openyuanrong.obs.cn-southwest-2.myhuaweicloud.com/daily_build/index.html"

JIUWENSWARM_VERSION=""
JIUWENSWARM_BASE=""
JIUWENSWARM_PACKAGES=()

MANAGER_VERSION=""
MANAGER_PACKAGES=()

OPENYUANRONG_VERSION=""
OPENYUANRONG_BASE=""
OPENYUANRONG_PACKAGES=()

CLIENT_TUI_PACKAGES=()
SERVER_PACKAGES=()

TUI_LAUNCHER_DIR="${PROJECT_ROOT}/tui-launcher"
TUI_LAUNCHER_VERSION="0.1.0"
TUI_LAUNCHER_PACKAGES=()

usage() {
  cat <<EOF
Usage: $(basename "$0") [daily|release] [options]

Build AgentOS distribution packages.

Arguments:
  daily|release    Build mode (default: daily)
                   daily   - download daily build artifacts from OBS
                   release - download release artifacts from gitcode/OBS

Options:
  --cp-tag TAG                        Python ABI tag for yuanrong wheels (default: cp311)
  --yuanrong-release-version VER      Yuanrong release version (default: 0.9.0) for release mode
  --jiuwenswarm-release-version VER   JiuwenSwarm release version (default: 0.2.2) for release mode
  --jiuwenswarm-release-git-tag TAG   JiuwenSwarm git release tag (default: JiuwenSwarm0.2.2) for release mode
  --yuanrong-daily-version VER        Yuanrong daily package version (default: 9.9.9) for daily mode
  --yr-schedule-time TIME             Yuanrong daily build schedule time (default: latest openeuler from index) for daily mode
  --yr-release-download-base URL      Yuanrong release download base URL (default: OBS release path from version/arch) for release mode
  --download-jobs N                   Max parallel downloads (default: 3)
  -h, --help                          Show this help

Examples:
  $(basename "$0")
  $(basename "$0") daily
  $(basename "$0") daily --yr-schedule-time 202607101255
  $(basename "$0") daily --yuanrong-daily-version 9.9.9
  $(basename "$0") daily --download-jobs 1
  $(basename "$0") release --cp-tag cp311
  $(basename "$0") release --yuanrong-release-version 0.9.0 --jiuwenswarm-release-version 0.2.3 --jiuwenswarm-release-git-tag release_0.2.3
  $(basename "$0") release --yr-release-download-base https://openyuanrong.obs.cn-southwest-2.myhuaweicloud.com/release/0.9.0/openeuler/aarch64
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      daily|release)
        BUILD_MODE="$1"
        shift
        ;;
      --cp-tag)
        CP_TAG="$2"
        shift 2
        ;;
      --cp-tag=*)
        CP_TAG="${1#*=}"
        shift
        ;;
      --yuanrong-release-version)
        YUANRONG_RELEASE_VERSION="$2"
        shift 2
        ;;
      --yuanrong-release-version=*)
        YUANRONG_RELEASE_VERSION="${1#*=}"
        shift
        ;;
      --yuanrong-daily-version)
        YUANRONG_DAILY_VERSION="$2"
        shift 2
        ;;
      --yuanrong-daily-version=*)
        YUANRONG_DAILY_VERSION="${1#*=}"
        shift
        ;;
      --jiuwenswarm-release-version)
        JIUWENSWARM_RELEASE_VERSION="$2"
        shift 2
        ;;
      --jiuwenswarm-release-version=*)
        JIUWENSWARM_RELEASE_VERSION="${1#*=}"
        shift
        ;;
      --jiuwenswarm-release-git-tag)
        JIUWENSWARM_RELEASE_GIT_TAG="$2"
        shift 2
        ;;
      --jiuwenswarm-release-git-tag=*)
        JIUWENSWARM_RELEASE_GIT_TAG="${1#*=}"
        shift
        ;;
      --yr-schedule-time)
        YR_SCHEDULE_TIME="$2"
        shift 2
        ;;
      --yr-schedule-time=*)
        YR_SCHEDULE_TIME="${1#*=}"
        shift
        ;;
      --yr-release-download-base)
        YR_RELEASE_DOWNLOAD_BASE="$2"
        shift 2
        ;;
      --yr-release-download-base=*)
        YR_RELEASE_DOWNLOAD_BASE="${1#*=}"
        shift
        ;;
      --download-jobs)
        DOWNLOAD_JOBS="$2"
        shift 2
        ;;
      --download-jobs=*)
        DOWNLOAD_JOBS="${1#*=}"
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "error: unknown argument: $1" >&2
        usage >&2
        exit 1
        ;;
    esac
  done

  if [[ "${BUILD_MODE}" != "daily" && "${BUILD_MODE}" != "release" ]]; then
    echo "error: BUILD_MODE must be daily or release, got: ${BUILD_MODE}" >&2
    exit 1
  fi

  if ! [[ "${DOWNLOAD_JOBS}" =~ ^[1-9][0-9]*$ ]]; then
    echo "error: DOWNLOAD_JOBS must be a positive integer, got: ${DOWNLOAD_JOBS}" >&2
    exit 1
  fi
}

fetch_latest_yr_schedule_time() {
  local html schedule_time

  echo "  fetch latest openeuler build from: ${YUANRONG_DAILY_INDEX_URL}" >&2

  if command -v curl >/dev/null 2>&1; then
    html="$(curl -fsSL --no-progress-meter --retry 3 --retry-delay 2 --connect-timeout 30 --max-time 60 \
      "${YUANRONG_DAILY_INDEX_URL}")"
  elif command -v wget >/dev/null 2>&1; then
    html="$(wget -qO- "${YUANRONG_DAILY_INDEX_URL}")"
  else
    echo "error: curl or wget is required to fetch yuanrong daily index" >&2
    return 1
  fi

  schedule_time="$(printf '%s\n' "${html}" \
    | sed -n '/<h2>openeuler<\/h2>/,/<hr class="os-divider">/p' \
    | sed -n 's/.*<tr><td>\([0-9][0-9]*\)<\/td>.*/\1/p' \
    | head -1)"

  if [[ -z "${schedule_time}" ]]; then
    schedule_time="$(printf '%s\n' "${html}" \
      | grep -oE 'daily_build/[0-9]+/openeuler' \
      | head -1 \
      | sed -E 's|daily_build/([0-9]+)/openeuler|\1|')"
  fi

  if [[ -z "${schedule_time}" ]]; then
    echo "error: failed to parse latest openeuler build from ${YUANRONG_DAILY_INDEX_URL}" >&2
    return 1
  fi

  echo "${schedule_time}"
}

resolve_yr_schedule_time() {
  if [[ -n "${YR_SCHEDULE_TIME}" ]]; then
    echo "${YR_SCHEDULE_TIME}"
    return 0
  fi

  fetch_latest_yr_schedule_time
}

configure_daily() {
  local jiuwen_schedule_time yr_schedule_time

  jiuwen_schedule_time="$(date +%Y%m%d)17"
  yr_schedule_time="$(resolve_yr_schedule_time)"
  echo "  yuanrong daily build: ${yr_schedule_time}, version: ${YUANRONG_DAILY_VERSION}"

  JIUWENSWARM_VERSION="${jiuwen_schedule_time}"
  MANAGER_VERSION="$(date +%Y%m%d)"
  JIUWENSWARM_BASE="https://openjiuwen-ci.obs.cn-north-4.myhuaweicloud.com/jiuwenswarm_agent_os/package/daily/dist/${jiuwen_schedule_time}"

  JIUWENSWARM_PACKAGES=(
    "jiuwenswarm-${JIUWENSWARM_VERSION}-py3-none-any.whl"
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-linux_aarch64.whl"
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-linux_x86_64.whl"
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-win_amd64.whl"
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-macosx_11_0_arm64.whl"
  )

  OPENYUANRONG_VERSION="${YUANRONG_DAILY_VERSION}"
  OPENYUANRONG_BASE="https://openyuanrong.obs.cn-southwest-2.myhuaweicloud.com/daily_build/${yr_schedule_time}/openeuler/${ARCH}"

  OPENYUANRONG_PACKAGES=(
    "openyuanrong-${OPENYUANRONG_VERSION}-py3-none-manylinux_2_34_${ARCH}.whl"
    "openyuanrong_sdk-${OPENYUANRONG_VERSION}-${CP_TAG}-${CP_TAG}-manylinux_2_34_${ARCH}.whl"
    "openyuanrong_runtime-${OPENYUANRONG_VERSION}-${CP_TAG}-${CP_TAG}-manylinux_2_34_${ARCH}.whl"
    "openyuanrong_datasystem-${OPENYUANRONG_VERSION}-${CP_TAG}-${CP_TAG}-manylinux_2_34_${ARCH}.whl"
    "openyuanrong_functionsystem-${OPENYUANRONG_VERSION}-py3-none-manylinux_2_34_${ARCH}.whl"
    "openyuanrong_faas-${OPENYUANRONG_VERSION}-${CP_TAG}-${CP_TAG}-manylinux_2_34_${ARCH}.whl"
    "agent_dx_executor-${OPENYUANRONG_VERSION}-py3-none-any.whl"
  )

  CLIENT_TUI_PACKAGES=(
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-macosx_11_0_arm64.whl"
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-win_amd64.whl"
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-linux_aarch64.whl"
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-linux_x86_64.whl"
  )

  TUI_LAUNCHER_PACKAGES=(
    "agentos_tui_launcher-${TUI_LAUNCHER_VERSION}-py3-none-macosx_11_0_arm64.whl"
    "agentos_tui_launcher-${TUI_LAUNCHER_VERSION}-py3-none-win_amd64.whl"
    "agentos_tui_launcher-${TUI_LAUNCHER_VERSION}-py3-none-linux_aarch64.whl"
    "agentos_tui_launcher-${TUI_LAUNCHER_VERSION}-py3-none-linux_x86_64.whl"
  )

  SERVER_PACKAGES=(
    "jiuwenswarm-${JIUWENSWARM_VERSION}-py3-none-any.whl"
    "${OPENYUANRONG_PACKAGES[@]}"
  )

  JIUWENSWARM_GIT_TAG="agent_os"
}

configure_release() {
  JIUWENSWARM_VERSION="${JIUWENSWARM_RELEASE_VERSION}"
  OPENYUANRONG_VERSION="${YUANRONG_RELEASE_VERSION}"
  MANAGER_VERSION="latest"

  JIUWENSWARM_BASE="https://gitcode.com/openJiuwen/jiuwenswarm/releases/download/${JIUWENSWARM_RELEASE_GIT_TAG}"

  JIUWENSWARM_PACKAGES=(
    "jiuwenswarm-${JIUWENSWARM_VERSION}-py3-none-any.whl"
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-macosx_11_0_arm64.whl"
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-win_amd64.whl"
  )

   if [[ -n "${YR_RELEASE_DOWNLOAD_BASE}" ]]; then
    OPENYUANRONG_BASE="${YR_RELEASE_DOWNLOAD_BASE}/openeuler/${ARCH}"
  else
    OPENYUANRONG_BASE="https://openyuanrong.obs.cn-southwest-2.myhuaweicloud.com/release/${OPENYUANRONG_VERSION}/openeuler/${ARCH}"
  fi
  echo "yuanrong release download base: ${OPENYUANRONG_BASE}"

  OPENYUANRONG_PACKAGES=(
    "openyuanrong-${OPENYUANRONG_VERSION}-py3-none-manylinux_2_34_${ARCH}.whl"
    "openyuanrong_sdk-${OPENYUANRONG_VERSION}-${CP_TAG}-${CP_TAG}-manylinux_2_34_${ARCH}.whl"
    "openyuanrong_runtime-${OPENYUANRONG_VERSION}-${CP_TAG}-${CP_TAG}-manylinux_2_34_${ARCH}.whl"
    "openyuanrong_datasystem-${OPENYUANRONG_VERSION}-${CP_TAG}-${CP_TAG}-manylinux_2_34_${ARCH}.whl"
    "openyuanrong_functionsystem-${OPENYUANRONG_VERSION}-py3-none-manylinux_2_34_${ARCH}.whl"
    "openyuanrong_faas-${OPENYUANRONG_VERSION}-${CP_TAG}-${CP_TAG}-manylinux_2_34_${ARCH}.whl"
    "agent_dx_executor-${OPENYUANRONG_VERSION}-py3-none-any.whl"
  )

  CLIENT_TUI_PACKAGES=(
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-macosx_11_0_arm64.whl"
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-win_amd64.whl"
  )

  TUI_LAUNCHER_PACKAGES=(
    "agentos_tui_launcher-${TUI_LAUNCHER_VERSION}-py3-none-macosx_11_0_arm64.whl"
    "agentos_tui_launcher-${TUI_LAUNCHER_VERSION}-py3-none-win_amd64.whl"
    "agentos_tui_launcher-${TUI_LAUNCHER_VERSION}-py3-none-linux_aarch64.whl"
    "agentos_tui_launcher-${TUI_LAUNCHER_VERSION}-py3-none-linux_x86_64.whl"
  )

  SERVER_PACKAGES=(
    "jiuwenswarm-${JIUWENSWARM_VERSION}-py3-none-any.whl"
    "${OPENYUANRONG_PACKAGES[@]}"
  )

  JIUWENSWARM_GIT_TAG="${JIUWENSWARM_RELEASE_GIT_TAG}"
}

configure_build() {
  case "${BUILD_MODE}" in
    daily)
      configure_daily
      ;;
    release)
      configure_release
      ;;
  esac
}

download_file() {
  local url="$1"
  local dest="$2"
  local name attempt max_attempts=5
  name="$(basename "${dest}")"

  if [[ -f "${dest}" ]]; then
    echo "  skip (exists): ${name}"
    return 0
  fi

  echo "  download: ${name}"
  echo "    url: ${url}"

  local tmp="${dest}.part"

  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    if command -v curl >/dev/null 2>&1; then
      if curl -fsSL --no-progress-meter \
        -C - \
        --connect-timeout 30 \
        --max-time 0 \
        -o "${tmp}" "${url}"; then
        break
      fi
    elif command -v wget >/dev/null 2>&1; then
      if wget -c --tries=1 --timeout=30 -O "${tmp}" "${url}"; then
        break
      fi
    else
      echo "error: curl or wget is required" >&2
      return 1
    fi

    if (( attempt < max_attempts )); then
      echo "  retry (${attempt}/${max_attempts}): ${name}" >&2
      sleep $((attempt * 3))
    else
      rm -f "${tmp}"
      echo "error: failed to download ${name}" >&2
      echo "  url: ${url}" >&2
      return 1
    fi
  done

  if [[ ! -s "${tmp}" ]]; then
    rm -f "${tmp}"
    echo "error: downloaded file is empty: ${name}" >&2
    echo "  url: ${url}" >&2
    return 1
  fi

  mv "${tmp}" "${dest}"
}

download_packages() {
  local base_url="$1"
  local dest_dir="$2"
  shift 2
  local packages=("$@")
  local -a pids=()
  local pkg running=0 failed=0

  for pkg in "${packages[@]}"; do
    while (( running >= DOWNLOAD_JOBS )); do
      if ! wait -n; then
        failed=1
      fi
      ((running--)) || true
    done

    download_file "${base_url}/${pkg}" "${dest_dir}/${pkg}" &
    pids+=("$!")
    ((running++)) || true
  done

  for pid in "${pids[@]}"; do
    if ! wait "${pid}"; then
      failed=1
    fi
  done

  return "${failed}"
}

build_jiuwenswarm() {
  echo "==> build_jiuwenswarm (${BUILD_MODE})"
  mkdir -p "${DOWNLOAD_DIR}/jiuwenswarm"

  git clone -b "${JIUWENSWARM_GIT_TAG}" https://gitcode.com/openJiuwen/jiuwenswarm.git "${DOWNLOAD_DIR}/jiuwenswarm_src"

  download_packages \
    "${JIUWENSWARM_BASE}" \
    "${DOWNLOAD_DIR}/jiuwenswarm" \
    "${JIUWENSWARM_PACKAGES[@]}"
}

build_openyuanrong() {
  echo "==> build_openyuanrong (${BUILD_MODE}, cp_tag=${CP_TAG})"
  mkdir -p "${DOWNLOAD_DIR}/openyuanrong"

  download_packages \
    "${OPENYUANRONG_BASE}" \
    "${DOWNLOAD_DIR}/openyuanrong" \
    "${OPENYUANRONG_PACKAGES[@]}"
}

build_agent_gateway() {
  echo "==> build_agent_gateway"
  mkdir -p "${DOWNLOAD_DIR}/agent-gateway"

  # a2x-registry 仅支持日构建，路径中的时固定为 19 点（后两位）；build.sh 可能在 19 点前或后执行，
  # 因此先尝试当天，找不到再尝试前一天
  local day whl_url found=0
  local daily_base="https://openjiuwen-ci.obs.cn-north-4.myhuaweicloud.com/agent-protocol/package/daily/dist"

  for day in "$(date +%Y%m%d)" "$(date -d "1 day ago" +%Y%m%d)"; do
    whl_url="${daily_base}/${day}19/a2x_registry-${REGISTRY_WHL_VERSION}-py3-none-any.whl"
    if curl -fsSI --connect-timeout 10 --max-time 30 "${whl_url}" >/dev/null 2>&1; then
      found=1
      break
    fi
  done

  if (( found != 1 )); then
    echo "error: failed to locate a2x_registry daily build for today or yesterday" >&2
    return 1
  fi

  download_file "${whl_url}" "${DOWNLOAD_DIR}/agent-gateway/a2x_registry-${REGISTRY_WHL_VERSION}-py3-none-any.whl"
}

build_conch() {
  echo "==> build_conch"
}

build_tui_launcher() {
  echo "==> build_tui_launcher (version=${TUI_LAUNCHER_VERSION})"
  local dist_dir="${DOWNLOAD_DIR}/tui-launcher"
  mkdir -p "${dist_dir}"

  # 使用 pip wheel 构建 tui-launcher 的 wheel 包（不下载依赖）
  # 构建产物放在 DOWNLOAD_DIR/tui-launcher 下，后续 pack 阶段会将其与 jiuwenswarm_tui 放在同一目录
  if command -v python >/dev/null 2>&1; then
    python -m pip wheel --no-deps -w "${dist_dir}" "${TUI_LAUNCHER_DIR}"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m pip wheel --no-deps -w "${dist_dir}" "${TUI_LAUNCHER_DIR}"
  else
    echo "error: python is required to build tui-launcher" >&2
    return 1
  fi

  # pip wheel 构建出 py3-none-any 的纯 Python wheel，此处复制为各平台命名的 wheel，
  # 与 jiuwenswarm_tui 保持一致的多平台打包方式
  local base_whl=""
  for whl in "${dist_dir}"/*.whl; do
    if [[ -f "${whl}" ]]; then
      base_whl="${whl}"
      echo "  built: $(basename "${whl}")"
      break
    fi
  done

  if [[ -z "${base_whl}" ]]; then
    echo "error: tui-launcher wheel not found after build" >&2
    return 1
  fi

  for pkg in "${TUI_LAUNCHER_PACKAGES[@]}"; do
    cp "${base_whl}" "${dist_dir}/${pkg}"
    echo "  created: ${pkg}"
  done
}

build_manager_app() {
  echo "==> build_manager_app (version=${MANAGER_VERSION})"

  local cp_deployment="${PROJECT_ROOT}/control-panel/deploy"
  if [[ ! -d "${cp_deployment}" ]]; then
    echo "error: manager deployment directory not found: ${cp_deployment}" >&2
    exit 1
  fi
  MANAGER_PACKAGES=("${cp_deployment}")
}

pack() {
  echo "==> pack"
  mkdir -p "${BUILD_DIR}"

  if [[ ! -d "${DEPLOY_DIR}" ]]; then
    echo "error: deploy directory not found: ${DEPLOY_DIR}" >&2
    exit 1
  fi

  local client_staging="${BUILD_DIR}/staging/client"
  local server_staging="${BUILD_DIR}/staging/server"
  local manager_staging="${BUILD_DIR}/staging/manager"

  rm -rf "${BUILD_DIR}/staging"
  mkdir -p "${client_staging}" "${server_staging}/deploy" "${manager_staging}"

  for pkg in "${CLIENT_TUI_PACKAGES[@]}"; do
    cp "${DOWNLOAD_DIR}/jiuwenswarm/${pkg}" "${client_staging}/"
  done

  # tui-launcher whl 与 jiuwenswarm_tui 放在同一目录（client 包），因为 tui-launcher 依赖 jiuwenswarm 运行时
  for pkg in "${TUI_LAUNCHER_PACKAGES[@]}"; do
    cp "${DOWNLOAD_DIR}/tui-launcher/${pkg}" "${client_staging}/"
  done

  for pkg in "${SERVER_PACKAGES[@]}"; do
    if [[ "${pkg}" == jiuwenswarm-* ]]; then
      cp "${DOWNLOAD_DIR}/jiuwenswarm/${pkg}" "${server_staging}/"
    else
      cp "${DOWNLOAD_DIR}/openyuanrong/${pkg}" "${server_staging}/"
    fi
  done

  cp "${DOWNLOAD_DIR}/agent-gateway/"*.whl "${server_staging}/"

  cp -a "${DEPLOY_DIR}/." "${server_staging}/deploy/"
  cp -a "${DOWNLOAD_DIR}/jiuwenswarm_src/deploy/yuanrong/." "${server_staging}/deploy/jiuwenswarm/"

  for pkg in "${MANAGER_PACKAGES[@]}"; do
    cp -a "${pkg}" "${manager_staging}/"
  done

  local client_tgz="${BUILD_DIR}/AgentOS-Client.tgz"
  local server_tgz="${BUILD_DIR}/AgentOS-Server-${ARCH}.tgz"
  local manager_tgz="${BUILD_DIR}/AgentOS-Manager.tgz"

  tar -czf "${client_tgz}" -C "${client_staging}" .
  tar -czf "${server_tgz}" -C "${server_staging}" .
  tar -czf "${manager_tgz}" -C "${manager_staging}" .

  echo "  created: ${client_tgz}"
  echo "  created: ${server_tgz}"
  echo "  created: ${manager_tgz}"
}

clean() {
  echo "==> clean"
  rm -rf "${BUILD_DIR}"
  rm -rf "${DOWNLOAD_DIR}"
}

main() {
  parse_args "$@"
  configure_build

  local yr_version="${YUANRONG_DAILY_VERSION}"
  if [[ "${BUILD_MODE}" == "release" ]]; then
    yr_version="${YUANRONG_RELEASE_VERSION}"
  fi

  echo "AgentOS build (mode=${BUILD_MODE}, cp_tag=${CP_TAG}, arch=${ARCH}, manager_version=${MANAGER_VERSION}, yr_schedule=${YR_SCHEDULE_TIME:-auto}, yr_version=${yr_version}, yr_release_base=${YR_RELEASE_DOWNLOAD_BASE:-auto}, jw_git_tag=${JIUWENSWARM_RELEASE_GIT_TAG}, download_jobs=${DOWNLOAD_JOBS})"
  clean
  build_manager_app
  build_openyuanrong
  build_jiuwenswarm
  build_tui_launcher
  build_agent_gateway
  build_conch
  pack
  echo "done"
}

main "$@"
