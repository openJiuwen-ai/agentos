#!/usr/bin/env bash
# UT：验证 build.sh 关键常量
set -u

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/build/build.sh" >/dev/null 2>&1

[ "${JIUWENSWARM_VERSION}" = "0.2.2" ]   && echo "[PASS] JIUWENSWARM_VERSION"   || { echo "[FAIL] JIUWENSWARM_VERSION"; exit 1; }
[ "${OPENYUANRONG_VERSION}" = "0.8.0" ]  && echo "[PASS] OPENYUANRONG_VERSION" || { echo "[FAIL] OPENYUANRONG_VERSION"; exit 1; }
[ "${#JIUWENSWARM_PACKAGES[@]}" -eq 3 ]  && echo "[PASS] JIUWENSWARM_PACKAGES" || { echo "[FAIL] JIUWENSWARM_PACKAGES"; exit 1; }
[ "${#OPENYUANRONG_PACKAGES[@]}" -eq 5 ] && echo "[PASS] OPENYUANRONG_PACKAGES"|| { echo "[FAIL] OPENYUANRONG_PACKAGES"; exit 1; }

echo "UT done"
