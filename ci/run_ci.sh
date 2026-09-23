#!/bin/bash
# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# 用于开发者自测 UT/ST
# 用法：
#   ./ci/run_ci.sh                       # 跑全部（UT + ST）
#   ./ci/run_ci.sh --type=ut             # 仅跑 UT
#   ./ci/run_ci.sh --type=st             # 仅跑 ST
#   ./ci/run_ci.sh --skip_build=0        # 安装测试依赖（bats-core）
set -e

BASE_DIR=$(dirname "$(readlink -f "$0")")
WORKSPACE=$(cd "$BASE_DIR"; cd ../; pwd)

TEST_TYPE="all"
SKIP_BUILD=1
for para in $*; do
  if [[ $para == --type* ]]; then
    TEST_TYPE=$(echo "${para#*=}")
  elif [[ $para == --skip_build* ]]; then
    SKIP_BUILD=$(echo "${para#*=}")
  fi
done

echo "init AgentOS test env"
cd "${WORKSPACE}"

if [ "$SKIP_BUILD" -eq 1 ]; then
  echo "skip build environments"
else
  echo "no extra build step needed (UT/ST are pure shell)"
fi

echo "start test (type=${TEST_TYPE})"
cd "${WORKSPACE}"

run_ut() {
  echo "==> UT"
  bash tests/ut/test_build.sh
}

run_st() {
  echo "==> ST"
  bash tests/st/test_pipeline.sh
}

case "${TEST_TYPE}" in
  all)
    run_ut
    run_st
    ;;
  ut)
    run_ut
    ;;
  st)
    run_st
    ;;
  *)
    echo "error: unknown --type=${TEST_TYPE}, expected: all | ut | st" >&2
    exit 1
    ;;
esac

echo "done"
