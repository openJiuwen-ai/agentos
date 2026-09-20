#!/usr/bin/env bash
set -e

# AgentOS b050 交付产物打包脚本。详细说明（产物清单/archive 结构/路径规则/重构要点/依赖）见 README-v2.md。
# daily/release 共用 OBS archive.tar.gz 获取 jiuwenswarm/openyuanrong/agent-protocol/conch，client 包不区分架构（含全平台 jiuwenswarm_tui + agentos_tui_launcher），server 包按 ${ARCH} 打。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_DIR="${PROJECT_ROOT}/build/dist"
DOWNLOAD_DIR="${BUILD_DIR}/downloads"
DEPLOY_DIR="${PROJECT_ROOT}/deploy"

# build parameters（命令行必填，见 usage；parse_args 校验非空与取值）
BUILD_TYPE=""
BUILD_TARGET=""
# 目标产物架构；可用 ARCH=aarch64 覆盖（非交叉编译，仅下载对应 arch 预编译 wheel 打包）
ARCH="${ARCH:-$(uname -m)}"
# ./ build parameters

JIUWENSWARM_BASE=""             # jiuwenswarm archive 下载基址（configure_* 设置）
JIUWENSWARM_ARCHIVE_ROOT=""     # jiuwenswarm archive.tar.gz 解压根目录（pack 取 wheel）
JIUWENSWARM_DEPLOY_DIR=""       # jiuwenswarm archive 内 deploy.tar.gz 解压出的 deploy 目录（pack 取 deploy/yuanrong）

OPENYUANRONG_BASE=""            # openyuanrong archive 下载基址（configure_* 设置）
OPENYUANRONG_ARCHIVE_ROOT=""    # openyuanrong archive.tar.gz 解压根目录（pack 取 wheel）

AGENT_GATEWAY_BASE=""           # agent-protocol archive 下载基址（configure_* 设置）
AGENT_GATEWAY_ARCHIVE_ROOT=""    # agent-protocol archive.tar.gz 解压根目录（pack 取 wheel）

CONCH_BASE=""                   # conch archive 下载基址（configure_* 设置）
CONCH_ARCHIVE_ROOT=""           # conch archive.tar.gz 解压根目录（pack 取 rpm，沙箱模块）

CREDENTIAL_ROUTER_BASE=""       # credential_router archive 下载基址（configure_* 设置）
CREDENTIAL_ROUTER_ARCHIVE_ROOT=""  # credential_router archive.tar.gz 解压根目录（pack 取 credential-router*.tar.gz，平台相关）

TUI_LAUNCHER_DIR="${PROJECT_ROOT}/tui-launcher"
# 版本号取 tui-launcher/pyproject.toml 声明的 0.1.0（与 build.sh 一致；避免用 git 短 hash 导致 wheel 文件名版本号与内部 metadata 0.1.0 不一致，pip 校验/部署失败）
TUI_LAUNCHER_VERSION="0.1.0"
TUI_LAUNCHER_PACKAGES=()

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --build-type=TYPE      daily or release (必填)
  --build-target=TARGET  交付产品线分支 (必填)
  -h, --help             Show this help

Examples:
  $(basename "$0") --build-type=daily --build-target=agentos_b050
  $(basename "$0") --build-type=release --build-target=agentos_b050

详见 README-v2.md（archive 结构/路径规则/构建流程）。
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --build-type=*)
        BUILD_TYPE="${1#*=}"
        shift
        ;;
      --build-target=*)
        BUILD_TARGET="${1#*=}"
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "error: unknown argument: $1" >&2
        echo "  (hint: use --key=value form, e.g. --build-type=release)" >&2
        usage >&2
        exit 1
        ;;
    esac
  done

  if [[ -z "${BUILD_TYPE}" ]]; then
    echo "error: --build-type is required (daily or release)" >&2
    exit 1
  fi
  if [[ "${BUILD_TYPE}" != "daily" && "${BUILD_TYPE}" != "release" ]]; then
    echo "error: BUILD_TYPE must be daily or release, got: ${BUILD_TYPE}" >&2
    exit 1
  fi

  if [[ -z "${BUILD_TARGET}" ]]; then
    echo "error: --build-target is required" >&2
    exit 1
  fi
}

configure_daily() {
  JIUWENSWARM_BASE="https://openjiuwen-ci.obs.cn-north-4.myhuaweicloud.com/jiuwenswarm/package/${BUILD_TYPE}/${BUILD_TARGET}/last_successful_build"
  OPENYUANRONG_BASE="https://openyuanrong.obs.cn-southwest-2.myhuaweicloud.com/${BUILD_TYPE}/${BUILD_TARGET}/last_successful_build"
  AGENT_GATEWAY_BASE="https://openjiuwen-ci.obs.cn-north-4.myhuaweicloud.com/agent-protocol/package/${BUILD_TYPE}/${BUILD_TARGET}/last_successful_build"
  CONCH_BASE="https://openjiuwen-ci.obs.cn-north-4.myhuaweicloud.com/conch/package/${BUILD_TYPE}/${BUILD_TARGET}/last_successful_build"
  CREDENTIAL_ROUTER_BASE="https://openjiuwen-ci.obs.cn-north-4.myhuaweicloud.com/credential_router/package/${BUILD_TYPE}/${BUILD_TARGET}/last_successful_build"

  TUI_LAUNCHER_PACKAGES=(
    "agentos_tui_launcher-${TUI_LAUNCHER_VERSION}-py3-none-macosx_11_0_arm64.whl"
    "agentos_tui_launcher-${TUI_LAUNCHER_VERSION}-py3-none-win_amd64.whl"
    "agentos_tui_launcher-${TUI_LAUNCHER_VERSION}-py3-none-linux_aarch64.whl"
    "agentos_tui_launcher-${TUI_LAUNCHER_VERSION}-py3-none-linux_x86_64.whl"
  )
}

configure_release() {
  JIUWENSWARM_BASE="https://openjiuwen-ci.obs.cn-north-4.myhuaweicloud.com/jiuwenswarm/package/${BUILD_TYPE}/${BUILD_TARGET}/last_successful_build"
  OPENYUANRONG_BASE="https://openyuanrong.obs.cn-southwest-2.myhuaweicloud.com/${BUILD_TYPE}/${BUILD_TARGET}/last_successful_build"
  AGENT_GATEWAY_BASE="https://openjiuwen-ci.obs.cn-north-4.myhuaweicloud.com/agent-protocol/package/${BUILD_TYPE}/${BUILD_TARGET}/last_successful_build"
  CONCH_BASE="https://openjiuwen-ci.obs.cn-north-4.myhuaweicloud.com/conch/package/${BUILD_TYPE}/${BUILD_TARGET}/last_successful_build"
  CREDENTIAL_ROUTER_BASE="https://openjiuwen-ci.obs.cn-north-4.myhuaweicloud.com/credential_router/package/${BUILD_TYPE}/${BUILD_TARGET}/last_successful_build"

  TUI_LAUNCHER_PACKAGES=(
    "agentos_tui_launcher-${TUI_LAUNCHER_VERSION}-py3-none-macosx_11_0_arm64.whl"
    "agentos_tui_launcher-${TUI_LAUNCHER_VERSION}-py3-none-win_amd64.whl"
    "agentos_tui_launcher-${TUI_LAUNCHER_VERSION}-py3-none-linux_aarch64.whl"
    "agentos_tui_launcher-${TUI_LAUNCHER_VERSION}-py3-none-linux_x86_64.whl"
  )
}

configure_build() {
  case "${BUILD_TYPE}" in
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

build_jiuwenswarm() {
  echo "==> build_jiuwenswarm (${BUILD_TYPE})"

  # 下载 archive.tar.gz 到带时间戳的临时目录解压，避免同名覆盖
  local timestamp tmp_dir archive_url
  timestamp="$(date +%Y%m%d%H%M%S)"
  tmp_dir="${BUILD_DIR}/tmp_jiuwenswarm_${timestamp}"
  archive_url="${JIUWENSWARM_BASE}/archive.tar.gz"

  mkdir -p "${tmp_dir}"
  download_file "${archive_url}" "${tmp_dir}/archive.tar.gz"

  tar --atime-preserve -xzf "${tmp_dir}/archive.tar.gz" -C "${tmp_dir}"
  rm -f "${tmp_dir}/archive.tar.gz"

  # archive.tar.gz 可能含 archive/ 顶层目录，也可能直接是平台目录
  JIUWENSWARM_ARCHIVE_ROOT="${tmp_dir}"
  if [[ -d "${tmp_dir}/archive" ]]; then
    JIUWENSWARM_ARCHIVE_ROOT="${tmp_dir}/archive"
  fi

  # 解压 deploy.tar.gz 获取 deploy 目录
  if [[ ! -f "${JIUWENSWARM_ARCHIVE_ROOT}/deploy.tar.gz" ]]; then
    echo "error: deploy.tar.gz not found in ${JIUWENSWARM_ARCHIVE_ROOT}" >&2
    return 1
  fi
  mkdir -p "${tmp_dir}/deploy_src"
  tar --atime-preserve -xzf "${JIUWENSWARM_ARCHIVE_ROOT}/deploy.tar.gz" -C "${tmp_dir}/deploy_src"
  JIUWENSWARM_DEPLOY_DIR="${tmp_dir}/deploy_src/deploy"
  if [[ ! -d "${JIUWENSWARM_DEPLOY_DIR}" ]]; then
    echo "error: deploy directory not found after extracting deploy.tar.gz" >&2
    return 1
  fi
}

build_openyuanrong() {
  echo "==> build_openyuanrong (${BUILD_TYPE})"

  # 下载 archive.tar.gz 到带时间戳的临时目录解压（与 build_jiuwenswarm 同模式）
  local timestamp tmp_dir archive_url
  timestamp="$(date +%Y%m%d%H%M%S)"
  tmp_dir="${BUILD_DIR}/tmp_openyuanrong_${timestamp}"
  archive_url="${OPENYUANRONG_BASE}/archive.tar.gz"

  mkdir -p "${tmp_dir}"
  download_file "${archive_url}" "${tmp_dir}/archive.tar.gz"

  tar --atime-preserve -xzf "${tmp_dir}/archive.tar.gz" -C "${tmp_dir}"
  rm -f "${tmp_dir}/archive.tar.gz"

  # archive.tar.gz 含 archive/ 顶层目录
  OPENYUANRONG_ARCHIVE_ROOT="${tmp_dir}"
  if [[ -d "${tmp_dir}/archive" ]]; then
    OPENYUANRONG_ARCHIVE_ROOT="${tmp_dir}/archive"
  fi

  # 校验平台目录存在
  if [[ ! -d "${OPENYUANRONG_ARCHIVE_ROOT}/${ARCH}" ]]; then
    echo "error: ${ARCH} directory not found in ${OPENYUANRONG_ARCHIVE_ROOT}" >&2
    return 1
  fi
}

build_agent_gateway() {
  echo "==> build_agent_gateway (${BUILD_TYPE})"

  # 下载 archive.tar.gz 到带时间戳的临时目录解压（与 build_jiuwenswarm/build_openyuanrong 同模式）
  local timestamp tmp_dir archive_url
  timestamp="$(date +%Y%m%d%H%M%S)"
  tmp_dir="${BUILD_DIR}/tmp_agent_gateway_${timestamp}"
  archive_url="${AGENT_GATEWAY_BASE}/archive.tar.gz"

  mkdir -p "${tmp_dir}"
  download_file "${archive_url}" "${tmp_dir}/archive.tar.gz"

  tar --atime-preserve -xzf "${tmp_dir}/archive.tar.gz" -C "${tmp_dir}"
  rm -f "${tmp_dir}/archive.tar.gz"

  # archive.tar.gz 含 archive/ 顶层目录
  AGENT_GATEWAY_ARCHIVE_ROOT="${tmp_dir}"
  if [[ -d "${tmp_dir}/archive" ]]; then
    AGENT_GATEWAY_ARCHIVE_ROOT="${tmp_dir}/archive"
  fi
}

build_conch() {
  echo "==> build_conch (${BUILD_TYPE})"

  # 下载 archive.tar.gz 到带时间戳的临时目录解压（与 build_jiuwenswarm/build_openyuanrong 同模式）
  # conch 为沙箱相关模块，产物为 rpm：archive/<arch>/*.rpm（平台相关）+ archive/*.rpm（平台无关 none）
  local timestamp tmp_dir archive_url
  timestamp="$(date +%Y%m%d%H%M%S)"
  tmp_dir="${BUILD_DIR}/tmp_conch_${timestamp}"
  archive_url="${CONCH_BASE}/archive.tar.gz"

  mkdir -p "${tmp_dir}"
  download_file "${archive_url}" "${tmp_dir}/archive.tar.gz"

  tar --atime-preserve -xzf "${tmp_dir}/archive.tar.gz" -C "${tmp_dir}"
  rm -f "${tmp_dir}/archive.tar.gz"

  # archive.tar.gz 含 archive/ 顶层目录
  CONCH_ARCHIVE_ROOT="${tmp_dir}"
  if [[ -d "${tmp_dir}/archive" ]]; then
    CONCH_ARCHIVE_ROOT="${tmp_dir}/archive"
  fi

  # 校验平台目录存在（按 ${ARCH} 取平台相关 rpm）
  if [[ ! -d "${CONCH_ARCHIVE_ROOT}/${ARCH}" ]]; then
    echo "error: ${ARCH} directory not found in ${CONCH_ARCHIVE_ROOT}" >&2
    return 1
  fi
}

build_credential_router() {
  echo "==> build_credential_router (${BUILD_TYPE})"

  # 下载 archive.tar.gz 到带时间戳的临时目录解压（与 build_jiuwenswarm/build_openyuanrong 同模式）
  # credential_router 产物为 tar.gz：archive/<arch>/credential-router*.tar.gz（平台相关，按 ${ARCH} 取）
  local timestamp tmp_dir archive_url
  timestamp="$(date +%Y%m%d%H%M%S)"
  tmp_dir="${BUILD_DIR}/tmp_credential_router_${timestamp}"
  archive_url="${CREDENTIAL_ROUTER_BASE}/archive.tar.gz"

  mkdir -p "${tmp_dir}"
  download_file "${archive_url}" "${tmp_dir}/archive.tar.gz"

  tar --atime-preserve -xzf "${tmp_dir}/archive.tar.gz" -C "${tmp_dir}"
  rm -f "${tmp_dir}/archive.tar.gz"

  # archive.tar.gz 含 archive/ 顶层目录
  CREDENTIAL_ROUTER_ARCHIVE_ROOT="${tmp_dir}"
  if [[ -d "${tmp_dir}/archive" ]]; then
    CREDENTIAL_ROUTER_ARCHIVE_ROOT="${tmp_dir}/archive"
  fi

  # 校验平台目录存在（按 ${ARCH} 取平台相关 credential-router*.tar.gz）
  if [[ ! -d "${CREDENTIAL_ROUTER_ARCHIVE_ROOT}/${ARCH}" ]]; then
    echo "error: ${ARCH} directory not found in ${CREDENTIAL_ROUTER_ARCHIVE_ROOT}" >&2
    return 1
  fi
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
    cp -p "${base_whl}" "${dist_dir}/${pkg}"
    echo "  created: ${pkg}"
  done
}

pack() {
  echo "==> pack"
  mkdir -p "${BUILD_DIR}"

  if [[ ! -d "${DEPLOY_DIR}" ]]; then
    echo "error: deploy directory not found: ${DEPLOY_DIR}" >&2
    exit 1
  fi

  local server_staging="${BUILD_DIR}/staging/server"

  rm -rf "${BUILD_DIR}/staging"
  mkdir -p "${server_staging}/deploy"

  # ---- client 打包（不区分架构：把全平台 jiuwenswarm_tui + agentos_tui_launcher 打到一起，命名/逻辑同 build.sh 的 AgentOS-Client.tgz；daily/release 同逻辑）----
  local client_staging="${BUILD_DIR}/staging/client"
  mkdir -p "${client_staging}"

  # jiuwenswarm_tui：OBS archive 按 CPU 架构族归类（x86_64/ 含 linux_x86_64+win_amd64，aarch64/ 含 linux_aarch64+macosx_arm64）
  # 收齐两个架构目录下所有 jiuwenswarm_tui wheel 一并打入 client 包（不再按 ${ARCH} 单取 linux 平台）
  local tui_whl tui_found=0
  for tui_whl in "${JIUWENSWARM_ARCHIVE_ROOT}/x86_64"/jiuwenswarm_tui-*.whl \
                 "${JIUWENSWARM_ARCHIVE_ROOT}/aarch64"/jiuwenswarm_tui-*.whl; do
    [[ -e "${tui_whl}" ]] || continue
    cp -p "${tui_whl}" "${client_staging}/"
    tui_found=1
  done
  if [[ "${tui_found}" -eq 0 ]]; then
    echo "error: no jiuwenswarm_tui wheel found in ${JIUWENSWARM_ARCHIVE_ROOT}/{x86_64,aarch64}" >&2
    exit 1
  fi

  # agentos_tui_launcher：build_tui_launcher 已按 TUI_LAUNCHER_PACKAGES 列表生成 4 个平台命名副本（macosx/win/linux_aarch64/linux_x86_64），全部打入 client 包
  local launcher_pkg launcher_found=0
  for launcher_pkg in "${TUI_LAUNCHER_PACKAGES[@]}"; do
    if [[ -f "${DOWNLOAD_DIR}/tui-launcher/${launcher_pkg}" ]]; then
      cp -p "${DOWNLOAD_DIR}/tui-launcher/${launcher_pkg}" "${client_staging}/"
      launcher_found=1
    fi
  done
  if [[ "${launcher_found}" -eq 0 ]]; then
    echo "error: no tui-launcher wheel found in ${DOWNLOAD_DIR}/tui-launcher" >&2
    exit 1
  fi

  tar --atime-preserve -czf "${BUILD_DIR}/AgentOS-Client.tgz" -C "${client_staging}" .
  echo "  created: ${BUILD_DIR}/AgentOS-Client.tgz"

  # ---- server 打包 ----
  # jiuwenswarm 平台无关 wheel 从 jiuwenswarm archive 根目录取
  local server_whl found=0
  for server_whl in "${JIUWENSWARM_ARCHIVE_ROOT}"/jiuwenswarm-*-py3-none-any.whl; do
    [[ -e "${server_whl}" ]] || continue
    cp -p "${server_whl}" "${server_staging}/"
    found=1
  done
  if [[ "${found}" -eq 0 ]]; then
    echo "error: no platform-independent jiuwenswarm wheel found in ${JIUWENSWARM_ARCHIVE_ROOT}" >&2
    exit 1
  fi

  # openyuanrong：平台相关 wheel 从 openyuanrong archive ${ARCH} 目录取，平台无关（agent_dx_executor）从根目录取
  cp -p "${OPENYUANRONG_ARCHIVE_ROOT}/${ARCH}"/*.whl "${server_staging}/"
  cp -p "${OPENYUANRONG_ARCHIVE_ROOT}"/*.whl "${server_staging}/"

  cp -p "${AGENT_GATEWAY_ARCHIVE_ROOT}"/*.whl "${server_staging}/"

  # conch：平台相关 rpm 从 conch archive ${ARCH} 目录取（build_conch 已校验目录），打入 server 包根目录与各 whl 同级
  cp -p "${CONCH_ARCHIVE_ROOT}/${ARCH}"/*.rpm "${server_staging}/"
  # 平台无关（none）rpm 在 archive 根目录，如有则一并打入（当前 conch archive 无 none rpm，跳过）
  local none_rpm
  for none_rpm in "${CONCH_ARCHIVE_ROOT}"/*.rpm; do
    [[ -e "${none_rpm}" ]] || continue
    cp -p "${none_rpm}" "${server_staging}/"
  done

  # credential_router：平台相关 credential-router 开头的 .tar.gz 从 credential_router archive ${ARCH} 目录取（build_credential_router 已校验目录），打入 server 包根目录与各 whl/rpm 同级
  cp -p "${CREDENTIAL_ROUTER_ARCHIVE_ROOT}/${ARCH}"/credential-router*.tar.gz "${server_staging}/"
  # 平台无关（none）credential-router*.tar.gz 在 archive 根目录，如有则一并打入（当前 credential_router archive 无 none tar.gz，跳过）
  local none_credential_router
  for none_credential_router in "${CREDENTIAL_ROUTER_ARCHIVE_ROOT}"/credential-router*.tar.gz; do
    [[ -e "${none_credential_router}" ]] || continue
    cp -p "${none_credential_router}" "${server_staging}/"
  done

  cp -a "${DEPLOY_DIR}/." "${server_staging}/deploy/"
  # deploy/jiuwenswarm 取自 jiuwenswarm archive 内 deploy.tar.gz
  cp -a "${JIUWENSWARM_DEPLOY_DIR}/yuanrong/." "${server_staging}/deploy/jiuwenswarm/"

  local server_tgz="${BUILD_DIR}/AgentOS-Server-${ARCH}.tgz"

  tar --atime-preserve -czf "${server_tgz}" -C "${server_staging}" .

  echo "  created: ${server_tgz}"
}

collect_buildinfo() {
  echo "==> collect_buildinfo"

  # 收集各部件 archive 内名字含 buildinfo 关键字的构建信息文件到 AgentOS-Buildinfo 目录，
  # 再压缩为 AgentOS-Buildinfo.tgz（与 AgentOS-Server/AgentOS-Client 同级，位于 ${BUILD_DIR}）。
  # cp -p + tar --atime-preserve 保留各 buildinfo 源文件时间戳不变，便于版本回溯。
  # 仅收集下载拉取的各部件 archive（tui-launcher 为本地构建，无 buildinfo）。
  local buildinfo_staging="${BUILD_DIR}/staging/AgentOS-Buildinfo"
  rm -rf "${buildinfo_staging}"
  mkdir -p "${buildinfo_staging}"

  # 各部件名称与其 archive 根目录（名称仅用于同名冲突时加前缀，避免覆盖丢失）
  local -a components=(
    "jiuwenswarm|${JIUWENSWARM_ARCHIVE_ROOT}"
    "openyuanrong|${OPENYUANRONG_ARCHIVE_ROOT}"
    "agent-gateway|${AGENT_GATEWAY_ARCHIVE_ROOT}"
    "conch|${CONCH_ARCHIVE_ROOT}"
    "credential-router|${CREDENTIAL_ROUTER_ARCHIVE_ROOT}"
  )

  local entry comp_name archive_root buildinfo_file dest_name found=0

  for entry in "${components[@]}"; do
    comp_name="${entry%%|*}"
    archive_root="${entry#*|}"
    # archive 根目录在对应 build_* 阶段已设置并校验；此处额外判空兜底
    [[ -z "${archive_root}" || ! -d "${archive_root}" ]] && continue

    # 递归查找名字含 buildinfo 关键字的文件（-iname 不区分大小写，兼容 buildinfor 命名）
    while IFS= read -r -d '' buildinfo_file; do
      dest_name="$(basename "${buildinfo_file}")"
      # 同名冲突时加部件名前缀，避免覆盖丢失
      if [[ -e "${buildinfo_staging}/${dest_name}" ]]; then
        dest_name="${comp_name}-${dest_name}"
      fi
      cp -p "${buildinfo_file}" "${buildinfo_staging}/${dest_name}"
      echo "  collected: ${dest_name} (from ${comp_name})"
      found=1
    done < <(find "${archive_root}" -type f -iname '*buildinfo*' -print0)
  done

  # 纳入 agent-os 主仓 buildinfo（CI 流水线生成于 build/ 目录，模糊匹配 build/ 下所有名字含 buildinfo 关键字的文件）
  # 只扫 ${SCRIPT_DIR} 顶层（非递归），避免误纳入 build/dist/ 等子目录
  while IFS= read -r -d '' buildinfo_file; do
    local main_dest_name
    main_dest_name="$(basename "${buildinfo_file}")"
    if [[ -e "${buildinfo_staging}/${main_dest_name}" ]]; then
      main_dest_name="agent-os-${main_dest_name}"
    fi
    cp -p "${buildinfo_file}" "${buildinfo_staging}/${main_dest_name}"
    echo "  collected: ${main_dest_name} (from agent-os)"
    found=1
  done < <(find "${SCRIPT_DIR}" -maxdepth 1 -type f -iname '*buildinfo*' -print0)

  if [[ "${found}" -eq 0 ]]; then
    echo "  warning: no buildinfo file found in any component archive" >&2
  fi

  # 压缩为 AgentOS-Buildinfo.tgz，与 AgentOS-Server-${ARCH}.tgz / AgentOS-Client.tgz 同级目录
  local buildinfo_tgz="${BUILD_DIR}/AgentOS-Buildinfo.tgz"
  tar --atime-preserve -czf "${buildinfo_tgz}" -C "${BUILD_DIR}/staging" AgentOS-Buildinfo
  echo "  created: ${buildinfo_tgz}"
}

clean() {
  echo "==> clean"
  rm -rf "${BUILD_DIR}"
  rm -rf "${DOWNLOAD_DIR}"
}

main() {
  parse_args "$@"
  configure_build

  echo "AgentOS build (build_type=${BUILD_TYPE}, build_target=${BUILD_TARGET}, arch=${ARCH})"
  clean                                # 清空 build/dist/（含 downloads 和 staging）
  build_openyuanrong                   # 下载并解压 OBS archive.tar.gz（openyuanrong wheels）
  build_jiuwenswarm                    # 下载并解压 OBS archive.tar.gz（jiuwenswarm wheels + deploy）
  build_tui_launcher                   # pip wheel 本地构建 tui-launcher（生成多平台命名副本）
  build_agent_gateway                  # 下载并解压 OBS archive.tar.gz（a2x_registry wheel）
  build_conch                          # 下载并解压 OBS archive.tar.gz（conch 沙箱模块 rpm）
  build_credential_router             # 下载并解压 OBS archive.tar.gz（credential-router 平台相关 tar.gz）
  pack                                 # 组装 client/server 两个 tgz 产物
  collect_buildinfo                    # 收集各子模块 buildinfo + agent-os 主仓 buildinfo(CI 生成) 一起打包到 AgentOS-Buildinfo.tgz
  echo "done"
}

main "$@"
