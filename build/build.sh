#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_DIR="${PROJECT_ROOT}/build/dist"
DOWNLOAD_DIR="${BUILD_DIR}/downloads"
DEPLOY_DIR="${PROJECT_ROOT}/deploy"

JIUWENSWARM_VERSION="0.2.2"
OPENYUANRONG_VERSION="0.8.0"

JIUWENSWARM_BASE="https://gitcode.com/openJiuwen/jiuwenswarm/releases/download/JiuwenSwarm${JIUWENSWARM_VERSION}"

JIUWENSWARM_PACKAGES=(
  "jiuwenswarm-${JIUWENSWARM_VERSION}-py3-none-any.whl"
  "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-macosx_11_0_arm64.whl"
  "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-win_amd64.whl"
)

OPENYUANRONG_BASE="https://openyuanrong.obs.cn-southwest-2.myhuaweicloud.com/release/${OPENYUANRONG_VERSION}/linux/aarch64"

OPENYUANRONG_PACKAGES=(
  "openyuanrong_functionsystem-${OPENYUANRONG_VERSION}-py3-none-manylinux_2_34_aarch64.whl"
  "openyuanrong-${OPENYUANRONG_VERSION}-cp311-cp311-manylinux_2_34_aarch64.whl"
  "openyuanrong_datasystem-${OPENYUANRONG_VERSION}-cp311-cp311-manylinux_2_34_aarch64.whl"
  "openyuanrong_faas-${OPENYUANRONG_VERSION}-cp311-cp311-manylinux_2_34_aarch64.whl"
  "openyuanrong_runtime-${OPENYUANRONG_VERSION}-cp311-cp311-manylinux_2_34_aarch64.whl"
)

CLIENT_TUI_PACKAGES=(
  "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-macosx_11_0_arm64.whl"
  "jiuwenswarm_tui-${JIUWENSWARM_VERSION}-py3-none-win_amd64.whl"
)

SERVER_PACKAGES=(
  "jiuwenswarm-${JIUWENSWARM_VERSION}-py3-none-any.whl"
  "${OPENYUANRONG_PACKAGES[@]}"
)

download_file() {
  local url="$1"
  local dest="$2"
  local name
  name="$(basename "${dest}")"

  if [[ -f "${dest}" ]]; then
    echo "  skip (exists): ${name}"
    return 0
  fi

  echo "  download: ${name}"
  echo "    url: ${url}"

  local tmp="${dest}.part"
  rm -f "${tmp}"

  if command -v curl >/dev/null 2>&1; then
    if ! curl -fSL --retry 3 --retry-delay 2 --connect-timeout 30 --max-time 600 \
      -o "${tmp}" "${url}"; then
      rm -f "${tmp}"
      echo "error: failed to download ${name}" >&2
      echo "  url: ${url}" >&2
      return 1
    fi
  elif command -v wget >/dev/null 2>&1; then
    if ! wget --tries=3 --timeout=30 --show-progress -O "${tmp}" "${url}"; then
      rm -f "${tmp}"
      echo "error: failed to download ${name}" >&2
      echo "  url: ${url}" >&2
      return 1
    fi
  else
    echo "error: curl or wget is required" >&2
    return 1
  fi

  if [[ ! -s "${tmp}" ]]; then
    rm -f "${tmp}"
    echo "error: downloaded file is empty: ${name}" >&2
    echo "  url: ${url}" >&2
    return 1
  fi

  mv "${tmp}" "${dest}"
}

build_jiuwenswarm() {
  echo "==> build_jiuwenswarm"
  mkdir -p "${DOWNLOAD_DIR}/jiuwenswarm"

  for pkg in "${JIUWENSWARM_PACKAGES[@]}"; do
    download_file \
      "${JIUWENSWARM_BASE}/${pkg}" \
      "${DOWNLOAD_DIR}/jiuwenswarm/${pkg}"
  done
}

build_openyuanrong() {
  echo "==> build_openyuanrong"
  mkdir -p "${DOWNLOAD_DIR}/openyuanrong"

  for pkg in "${OPENYUANRONG_PACKAGES[@]}"; do
    download_file \
      "${OPENYUANRONG_BASE}/${pkg}" \
      "${DOWNLOAD_DIR}/openyuanrong/${pkg}"
  done
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
  echo "AgentOS build"
  clean
  build_manager_app
  build_jiuwenswarm
  build_openyuanrong
  build_conch
  pack
  echo "done"
}

main "$@"
