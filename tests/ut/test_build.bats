#!/usr/bin/env bats
# build.sh 单元测试
# 运行：bats tests/ut/test_build.bats

setup() {
  SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)/build"
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/build.sh" >/dev/null 2>&1
}

@test "JIUWENSWARM_VERSION 固定为 0.2.2" {
  [ "${JIUWENSWARM_VERSION}" = "0.2.2" ]
}

@test "OPENYUANRONG_VERSION 固定为 0.8.0" {
  [ "${OPENYUANRONG_VERSION}" = "0.8.0" ]
}

@test "JIUWENSWARM_PACKAGES 包含 3 个 wheel" {
  [ "${#JIUWENSWARM_PACKAGES[@]}" -eq 3 ]
}

@test "OPENYUANRONG_PACKAGES 包含 5 个 wheel" {
  [ "${#OPENYUANRONG_PACKAGES[@]}" -eq 5 ]
}

@test "JIUWENSWARM_BASE 指向 gitcode release" {
  [[ "${JIUWENSWARM_BASE}" == *"gitcode.com/openJiuwen/jiuwenswarm/releases/download/JiuwenSwarm${JIUWENSWARM_VERSION}"* ]]
}

@test "OPENYUANRONG_BASE 指向华为云 OBS aarch64" {
  [[ "${OPENYUANRONG_BASE}" == *"openyuanrong.obs.cn-southwest-2.myhuaweicloud.com/release/${OPENYUANRONG_VERSION}/linux/aarch64" ]]
}

@test "download_file: 目标文件已存在时跳过下载" {
  local tmp
  tmp="$(mktemp -d)"
  local dest="${tmp}/existing.whl"
  touch "${dest}"

  run download_file "http://example.invalid/pkg" "${dest}"
  [ "$status" -eq 0 ]
  [[ "$output" == *"skip (exists)"* ]]

  rm -rf "${tmp}"
}

@test "download_file: URL 不可达时返回非零" {
  local tmp
  tmp="$(mktemp -d)"
  local dest="${tmp}/missing.whl"

  run download_file "http://example.invalid/does-not-exist.whl" "${dest}"
  [ "$status" -ne 0 ]
  [[ "$output" == *"failed to download"* ]]
  [ ! -f "${dest}" ]
  [ ! -f "${dest}.part" ]

  rm -rf "${tmp}"
}

@test "build_conch 与 build_manager_app 为占位函数且成功退出" {
  run build_conch
  [ "$status" -eq 0 ]
  run build_manager_app
  [ "$status" -eq 0 ]
}

@test "clean 删除 build/dist 目录" {
  local project_root
  project_root="$(cd "${SCRIPT_DIR}/.." && pwd)"
  mkdir -p "${project_root}/build/dist/downloads"
  run clean
  [ "$status" -eq 0 ]
  [ ! -d "${project_root}/build/dist" ]
}
