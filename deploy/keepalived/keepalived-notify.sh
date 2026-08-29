#!/bin/bash
# agentos-keepalived-notify
# keepalived notify_master / notify_backup / notify_fault 回调脚本。
#
# 分层设计：本脚本只是 VRRP 状态 → agentos 命令的"薄适配层"，
# 不感知任何具体管理面 unit（registry/gateway/web 等）。
# 管理面服务清单由 agentos.sh 的 MGMT_UNITS 统一维护，
# 本脚本仅调用 agentos.sh 提供的 `mgmt start|stop` 命令。
#
# 切换语义（幂等、可重入）:
#   MASTER  == 本机夺得 VIP  → agentos.sh mgmt start
#   BACKUP  == 本机失去 VIP  → agentos.sh mgmt stop
#   FAULT   == 实例故障      → agentos.sh mgmt stop
#
# 设计要点:
#   - 与管理面 unit 的 ExecStartPre(check-ingress-master) 协同：
#     启停由本回调驱动，ExecStartPre 再校验"本机是否真持有 VIP"作为二道防线。
#   - 管理面服务存活由 systemd 监控并异常拉起，keepalived 不做健康探测。
#   - 任何失败不阻塞 keepalived（始终 exit 0），仅记录日志。
#
# 环境变量（由 keepalived 传入）:
#   TYPE / INSTANCE / STATE(可选) — keepalived 标准 notify 参数

# agentos.sh 路径：install 时由 module.sh 注入（占位符替换为其 SCRIPT_DIR/agentos.sh，
# 即执行 install 时 agentos.sh 实际所在的 deploy/ 目录，不假定固定安装位置）。
AGENTOS_SH="@AGENTOS_SH@"

_log() { echo "[agentos-keepalived-notify] $(date '+%F %T') $*" >> /var/log/agentos/keepalived-notify.log; }

_mgmt() {
    local action="$1"
    if [ ! -f "${AGENTOS_SH}" ]; then
        _log "ERROR: agentos.sh not found at '${AGENTOS_SH}', cannot ${action} management plane (re-run install to refresh path)"
        return 0
    fi
    _log "invoking: agentos.sh mgmt ${action}"
    bash "${AGENTOS_SH}" mgmt "${action}" >> /var/log/agentos/keepalived-notify.log 2>&1 \
        || _log "WARN: agentos.sh mgmt ${action} returned non-zero"
}

TYPE="${TYPE:-${1:-}}"
INSTANCE="${INSTANCE:-${2:-}}"
# keepalived 1.x 用 TYPE, 2.x 用 STATE，兼容两者
if [ -z "${TYPE}" ]; then
    TYPE="${STATE:-}"
fi

case "${TYPE}" in
    MASTER)
        _log "transition to MASTER (instance='${INSTANCE}'), starting management plane"
        _mgmt start
        ;;
    BACKUP|FAULT)
        _log "transition to ${TYPE} (instance='${INSTANCE}'), stopping management plane"
        _mgmt stop
        ;;
    *)
        _log "unrecognized notify type '${TYPE}' (instance='${INSTANCE}'), ignoring"
        ;;
esac

exit 0
