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
JIUWENSWARM_RELEASE_VERSION="0.2.2"
YUANRONG_DAILY_VERSION="9.9.9"
YR_SCHEDULE_TIME=""
DOWNLOAD_JOBS=3
# ./ build parameters

YUANRONG_DAILY_INDEX_URL="https://openyuanrong.obs.cn-southwest-2.myhuaweicloud.com/daily_build/index.html"

JIUWENSWARM_VERSION=""
JIUWENSWARM_BASE=""
JIUWENSWARM_PACKAGES=()

OPENYUANRONG_VERSION=""
OPENYUANRONG_BASE=""
OPENYUANRONG_PACKAGES=()

CLIENT_TUI_PACKAGES=()
SERVER_PACKAGES=()

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
  --yuanrong-release-version VER      Yuanrong release version (default: 0.8.0) for release mode
  --jiuwenswarm-release-version VER   JiuwenSwarm release version (default: 0.2.2) for release mode
  --yuanrong-daily-version VER        Yuanrong daily package version (default: 9.9.9) for daily mode
  --yr-schedule-time TIME             Yuanrong daily build schedule time (default: latest openeuler from index) for daily mode
  --download-jobs N                   Max parallel downloads (default: 3)
  -h, --help                          Show this help

Examples:
  $(basename "$0")
  $(basename "$0") daily
  $(basename "$0") daily --yr-schedule-time 202607101255
  $(basename "$0") daily --yuanrong-daily-version 9.9.9
  $(basename "$0") daily --download-jobs 1
  $(basename "$0") release --cp-tag cp311
  $(basename "$0") release --yuanrong-release-version 0.8.0 --jiuwenswarm-release-version 0.2.2
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
      --yr-schedule-time)
        YR_SCHEDULE_TIME="$2"
        shift 2
        ;;
      --yr-schedule-time=*)
        YR_SCHEDULE_TIME="${1#*=}"
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
    | grep 'openeuler' \
    | head -1 \
    | sed -E 's/.*openeuler<\/td><td>([0-9]+)<\/td>.*/\1/')"

  if [[ -z "${schedule_time}" || "${schedule_time}" == *openeuler* ]]; then
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

  jiuwen_schedule_time="$(date +%Y%m%d)02"
  yr_schedule_time="$(resolve_yr_schedule_time)"
  echo "  yuanrong daily build: ${yr_schedule_time}, version: ${YUANRONG_DAILY_VERSION}"

  JIUWENSWARM_VERSION="${jiuwen_schedule_time}"
  JIUWENSWARM_BASE="https://openjiuwen-ci.obs.cn-north-4.myhuaweicloud.com/jiuwenswarm/package/daily/dist/${jiuwen_schedule_time}"

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
  )

  CLIENT_TUI_PACKAGES=(
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-macosx_11_0_arm64.whl"
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-win_amd64.whl"
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-linux_aarch64.whl"
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-linux_x86_64.whl"
  )

  SERVER_PACKAGES=(
    "jiuwenswarm-${JIUWENSWARM_VERSION}-py3-none-any.whl"
    "${OPENYUANRONG_PACKAGES[@]}"
  )
}

configure_release() {
  JIUWENSWARM_VERSION="${JIUWENSWARM_RELEASE_VERSION}"
  OPENYUANRONG_VERSION="${YUANRONG_RELEASE_VERSION}"

  JIUWENSWARM_BASE="https://gitcode.com/openJiuwen/jiuwenswarm/releases/download/JiuwenSwarm${JIUWENSWARM_VERSION}"

  JIUWENSWARM_PACKAGES=(
    "jiuwenswarm-${JIUWENSWARM_VERSION}-py3-none-any.whl"
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-macosx_11_0_arm64.whl"
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-win_amd64.whl"
  )

  OPENYUANRONG_BASE="https://openyuanrong.obs.cn-southwest-2.myhuaweicloud.com/release/${OPENYUANRONG_VERSION}/openeuler/${ARCH}"

  OPENYUANRONG_PACKAGES=(
    "openyuanrong-${OPENYUANRONG_VERSION}-py3-none-manylinux_2_34_${ARCH}.whl"
    "openyuanrong_sdk-${OPENYUANRONG_VERSION}-${CP_TAG}-${CP_TAG}-manylinux_2_34_${ARCH}.whl"
    "openyuanrong_runtime-${OPENYUANRONG_VERSION}-${CP_TAG}-${CP_TAG}-manylinux_2_34_${ARCH}.whl"
    "openyuanrong_datasystem-${OPENYUANRONG_VERSION}-${CP_TAG}-${CP_TAG}-manylinux_2_34_${ARCH}.whl"
    "openyuanrong_functionsystem-${OPENYUANRONG_VERSION}-py3-none-manylinux_2_34_${ARCH}.whl"
    "openyuanrong_faas-${OPENYUANRONG_VERSION}-${CP_TAG}-${CP_TAG}-manylinux_2_34_${ARCH}.whl"
  )

  CLIENT_TUI_PACKAGES=(
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-macosx_11_0_arm64.whl"
    "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-win_amd64.whl"
  )

  SERVER_PACKAGES=(
    "jiuwenswarm-${JIUWENSWARM_VERSION}-py3-none-any.whl"
    "${OPENYUANRONG_PACKAGES[@]}"
  )
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

build_conch() {
  echo "==> build_conch"
}

build_manager_app() {
  echo "==> build_manager_app"
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

  rm -rf "${BUILD_DIR}/staging"
  mkdir -p "${client_staging}" "${server_staging}/deploy"

  for pkg in "${CLIENT_TUI_PACKAGES[@]}"; do
    cp "${DOWNLOAD_DIR}/jiuwenswarm/${pkg}" "${client_staging}/"
  done

  for pkg in "${SERVER_PACKAGES[@]}"; do
    if [[ "${pkg}" == jiuwenswarm-* ]]; then
      cp "${DOWNLOAD_DIR}/jiuwenswarm/${pkg}" "${server_staging}/"
    else
      cp "${DOWNLOAD_DIR}/openyuanrong/${pkg}" "${server_staging}/"
    fi
  done

  cp -a "${DEPLOY_DIR}/." "${server_staging}/deploy/"

  local client_tgz="${BUILD_DIR}/AgentOS-Client.tgz"
  local server_tgz="${BUILD_DIR}/AgentOS-Server.tgz"

  tar -czf "${client_tgz}" -C "${client_staging}" .
  tar -czf "${server_tgz}" -C "${server_staging}" .

  echo "  created: ${client_tgz}"
  echo "  created: ${server_tgz}"
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

  echo "AgentOS build (mode=${BUILD_MODE}, cp_tag=${CP_TAG}, arch=${ARCH}, yr_schedule=${YR_SCHEDULE_TIME:-auto}, yr_version=${yr_version}, download_jobs=${DOWNLOAD_JOBS})"
  clean
  build_manager_app
  build_openyuanrong
  build_jiuwenswarm
  build_conch
  pack
  echo "done"
}

main "$@"
