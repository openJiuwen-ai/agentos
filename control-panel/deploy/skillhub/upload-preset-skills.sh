#!/bin/bash
set -euo pipefail
#
# upload-preset-skills.sh — 将一个包含多个 skill 的 zip 解压到固定目录后上传到 SkillHub
#
# 用法:
#   ./upload-preset-skills.sh                                    # 使用默认 zip: 同目录下 preset-skills.zip
#   ./upload-preset-skills.sh /path/to/skills.zip                # 指定 zip
#   ./upload-preset-skills.sh /path/to/skills.zip --host http://10.0.0.1:8098 --token sk-xxx
#
# 流程:
#   1. 接收 zip（默认同目录下 preset-skills.zip，内含 3 个预置 skill）
#   2. 解压到固定目录 EXTRACT_DIR（默认 /home/agentos/agent_preset/skills，持久保留供用户预装使用）
#   3. 校验：每个顶层目录须含 SKILL.md
#   4. 计算原 zip 的 sha256
#   5. 调用 SkillHub skill-import API（X-System-Token 鉴权）上传原 zip
#   6. 解析同步返回结果并打印
#
# 环境变量（必须显式传入或通过 --host/--token 参数指定）:
#   SKILLHUB_URL        SkillHub 前端地址，如 http://10.0.0.1:8098
#   SYSTEM_ADMIN_TOKEN  SkillHub 系统管理员令牌（X-System-Token 鉴权）
#   EXTRACT_DIR         解压目录，默认 /home/agentos/agent_preset/skills
#

# ----------------------------- 路径与配置 ----------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ZIP="${SCRIPT_DIR}/preset-skills.zip"
EXTRACT_DIR="/home/agentos/agent_preset/skills"

# 颜色输出
C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_CYAN=$'\033[36m'; C_RESET=$'\033[0m'
log()  { echo "${C_GREEN}[upload]${C_RESET} $*"; }
warn() { echo "${C_YELLOW}[warn]${C_RESET} $*"; }
err()  { echo "${C_RED}[error]${C_RESET} $*" >&2; }

# ----------------------------- 参数解析 ------------------------------------
ZIP_FILE="$DEFAULT_ZIP"
while [ $# -gt 0 ]; do
  case "$1" in
    --host) SKILLHUB_URL="$2"; shift 2 ;;
    --token) SYSTEM_ADMIN_TOKEN="$2"; shift 2 ;;
    *) ZIP_FILE="$1"; shift ;;
  esac
done

# 必须显式传入 SKILLHUB_URL 和 SYSTEM_ADMIN_TOKEN
[ -n "${SYSTEM_ADMIN_TOKEN:-}" ] || { err "未设置 SYSTEM_ADMIN_TOKEN（请通过 --token 参数或环境变量传入）"; exit 1; }
[ -n "${SKILLHUB_URL:-}" ] || { err "未设置 SKILLHUB_URL（请通过 --host 参数或环境变量传入）"; exit 1; }

# ----------------------------- 前置检查 ------------------------------------
command -v curl   >/dev/null 2>&1 || { err "需要 curl"; exit 1; }
command -v python3 >/dev/null 2>&1 || { err "需要 python3（用于解析结果）"; exit 1; }
command -v unzip  >/dev/null 2>&1 || { err "需要 unzip"; exit 1; }

[ -f "$ZIP_FILE" ] || { err "zip 文件不存在: $ZIP_FILE"; exit 1; }

# ----------------------------- 资源清理 ------------------------------------
RESP_FILE=""
cleanup() {
  [ -n "$RESP_FILE" ] && rm -f "$RESP_FILE"
}
trap cleanup EXIT

# ----------------------------- 1. 等待 SkillHub 就绪 -----------------------
# 兜底等待：被 skillhub.sh up 调用时，cmd_up 已 wait_healthy 通过，此处首次 curl 立即 break。
log "目标 SkillHub: $SKILLHUB_URL"
for i in $(seq 1 30); do
  curl -sf "${SKILLHUB_URL}/api/health" >/dev/null 2>&1 && break
  [ "$i" -eq 30 ] && { err "SkillHub 不可达: $SKILLHUB_URL （先用 skillhub.sh up 启动）"; exit 1; }
  sleep 2
done

# ----------------------------- 2. 解压到固定目录 ---------------------------
log "清空并解压到固定目录: $EXTRACT_DIR"
mkdir -p "$EXTRACT_DIR"
rm -rf "${EXTRACT_DIR}"/*    # 只删内容，不删目录本身（保护 bind mount inode）
unzip -q "$ZIP_FILE" -d "$EXTRACT_DIR"

# ----------------------------- 3. 校验 skill 目录结构 ----------------------
# 支持两种格式：
#   简单格式：entry/SKILL.md
#   标准格式：entry/plugin.yaml + entry/{name}/SKILL.md（name 取自 plugin.yaml）
# manifest.json 可选
shopt -s nullglob
skill_dirs=()
for d in "$EXTRACT_DIR"/*/; do
  d="${d%/}"
  if [ -f "$d/SKILL.md" ]; then
    # 简单格式
    skill_dirs+=("$(basename "$d")")
  elif [ -f "$d/plugin.yaml" ]; then
    # 标准格式：从 plugin.yaml 读 name，校验 {name}/SKILL.md 存在
    py_name="$(grep -E '^\s*name:' "$d/plugin.yaml" | head -1 | sed 's/^[[:space:]]*name:[[:space:]]*//;s/[[:space:]]*$//;s/^"\(.*\)"$/\1/;s/^'\''\(.*\)'\''$/\1/')"
    if [ -n "$py_name" ] && [ -f "$d/$py_name/SKILL.md" ]; then
      skill_dirs+=("$(basename "$d")")
    fi
  fi
done
shopt -u nullglob

if [ ${#skill_dirs[@]} -eq 0 ]; then
  err "未在 $EXTRACT_DIR 下找到任何有效的 skill 目录"
  err "期望结构（简单格式）: <zip>/skill-name/SKILL.md"
  err "期望结构（标准格式）: <zip>/skill-name/plugin.yaml + <zip>/skill-name/{name}/SKILL.md"
  exit 1
fi
log "发现 ${#skill_dirs[@]} 个 skill: ${skill_dirs[*]}"

# ----------------------------- 4. 计算 sha256 -----------------------------
SHA256="$(sha256sum "$ZIP_FILE" | awk '{print $1}')"
log "上传 zip: $ZIP_FILE  (sha256=$SHA256)"

# ----------------------------- 5. 上传到 SkillHub -------------------------
log "调用 skill-import API 上传（force=true）..."
RESP_FILE="$(mktemp)"
# fail_fast=false: zip 内多个 skill 时，单个失败不中断，继续处理剩余的，最终汇总结果
# --max-time 300: curl 整个请求（连接+传输+等待响应）超时上限 300 秒（skill-import 同步返回）
HTTP_CODE="$(curl -s -o "$RESP_FILE" -w '%{http_code}' \
  -X POST "${SKILLHUB_URL}/api/v1/plugins/skill-import" \
  -H "X-System-Token: ${SYSTEM_ADMIN_TOKEN}" \
  -H "X-Checksum-SHA256: ${SHA256}" \
  -F "file=@${ZIP_FILE}" \
  -F "force=true" \
  -F "fail_fast=false" \
  --max-time 300 )"

# ----------------------------- 6. 解析结果 --------------------------------
if [ "$HTTP_CODE" != "200" ]; then
  err "上传失败: HTTP $HTTP_CODE"
  cat "$RESP_FILE"; echo
  exit 1
fi

python3 - "$RESP_FILE" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    resp = json.load(f)
data = resp.get("data", {})
summary = data.get("summary", {})
print(f"\n{'='*44}")
print(f" 上传完成: {resp.get('message','')}")
print(f"{'='*44}")
print(f"  total  = {summary.get('total')}")
print(f"  ok     = {summary.get('ok')}")
print(f"  failed = {summary.get('failed')}")
print(f"  skipped= {summary.get('skipped')}")
print(f"{'-'*44}")
for r in data.get("results", []):
    mark = "OK" if r["status"] == "ok" else r["status"].upper()
    line = f"  [{mark:<7}] {r['entry']}"
    if r.get("version"):
        line += f"  v{r['version']}"
    if r.get("plugin_id"):
        line += f"  ({r['plugin_id']})"
    if r.get("error"):
        line += f"  -> {r['error']}"
    print(line)
print(f"{'='*44}")
failed = summary.get("failed", 0)
sys.exit(1 if failed > 0 else 0)
PY
RC=$?

echo
log "可在前端验证: ${C_CYAN}${SKILLHUB_URL}${C_RESET}  （登录后浏览市场）"
exit $RC
