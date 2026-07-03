#!/usr/bin/env bash
# 流水线系统测试：执行完整构建并校验产物
# 运行：bash tests/st/test_pipeline.sh
# 依赖：bash、curl 或 wget、tar
# 注意：需可访问外网（gitcode.com、华为云 OBS）
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BUILD_SH="${PROJECT_ROOT}/build/build.sh"
DIST_DIR="${PROJECT_ROOT}/build/dist"

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

pass() {
  echo "[PASS] $*"
}

echo "==> ST: AgentOS 构建流水线系统测试"

# 前置条件
[ -f "${BUILD_SH}" ] || fail "build.sh 不存在: ${BUILD_SH}"
command -v tar >/dev/null 2>&1 || fail "缺少 tar 命令"
command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 || fail "缺少 curl/wget"

pass "前置条件检查通过"

# 执行构建
echo "==> 执行 build.sh"
bash "${BUILD_SH}" || fail "build.sh 执行失败"
pass "build.sh 执行成功"

# 校验产物文件
[ -f "${DIST_DIR}/AgentOS-Client.tgz" ] || fail "缺少产物 AgentOS-Client.tgz"
[ -f "${DIST_DIR}/AgentOS-Server.tgz" ] || fail "缺少产物 AgentOS-Server.tgz"
pass "产物文件存在"

# 校验 Client 包内容
TMP_CLIENT="$(mktemp -d)"
tar -xzf "${DIST_DIR}/AgentOS-Client.tgz" -C "${TMP_CLIENT}"
client_wheels=( "$(find "${TMP_CLIENT}" -maxdepth 1 -name '*.whl')" )
[ "${#client_wheels[@]}" -ge 2 ] || fail "Client 包 wheel 数量异常: ${#client_wheels[@]}"
[[ -f "${TMP_CLIENT}/jiuwenswarm_tui-0.2.2-py3-none-macosx_11_0_arm64.whl" ]] || fail "Client 缺少 macOS arm64 TUI wheel"
[[ -f "${TMP_CLIENT}/jiuwenswarm_tui-0.2.2-py3-none-win_amd64.whl" ]] || fail "Client 缺少 Windows amd64 TUI wheel"
pass "Client 包内容校验通过（2 个 TUI wheel）"
rm -rf "${TMP_CLIENT}"

# 校验 Server 包内容
TMP_SERVER="$(mktemp -d)"
tar -xzf "${DIST_DIR}/AgentOS-Server.tgz" -C "${TMP_SERVER}"
[[ -f "${TMP_SERVER}/jiuwenswarm-0.2.2-py3-none-any.whl" ]] || fail "Server 缺少 jiuwenswarm 通用 wheel"
for pkg in \
  "openyuanrong_functionsystem-0.8.0-py3-none-manylinux_2_34_aarch64.whl" \
  "openyuanrong-0.8.0-cp311-cp311-manylinux_2_34_aarch64.whl" \
  "openyuanrong_datasystem-0.8.0-cp311-cp311-manylinux_2_34_aarch64.whl" \
  "openyuanrong_faas-0.8.0-cp311-cp311-manylinux_2_34_aarch64.whl" \
  "openyuanrong_runtime-0.8.0-cp311-cp311-manylinux_2_34_aarch64.whl"; do
  [[ -f "${TMP_SERVER}/${pkg}" ]] || fail "Server 缺少 ${pkg}"
done
[ -d "${TMP_SERVER}/deploy" ] || fail "Server 包缺少 deploy/ 目录"
[[ -f "${TMP_SERVER}/deploy/deploy.sh" ]] || fail "Server 包缺少 deploy/deploy.sh"
pass "Server 包内容校验通过（1 jiuwenswarm + 5 openYuanrong + deploy/）"
rm -rf "${TMP_SERVER}"

echo "==> ST: 全部系统测试通过"
