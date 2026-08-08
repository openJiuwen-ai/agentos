/**
 * cron 触发会话的 session_id → job_id 派生 — 纯函数,便于单测。
 *
 * 后端 scheduler 每次 cron 触发创建会话时,session_id = `cron_<hex毫秒>_<job_id>`
 * (jiuwenswarm/gateway/cron/scheduler.py:441)。故无需后端给 Session 加 cron_id 字段,
 * 前端解析 session_id 前缀 + 后缀即可派生归属 job(Phase 5 执行历史 job 归属)。
 */
const CRON_SESSION_PREFIX = 'cron_';

/** session_id 是否为 cron 触发会话(前缀 cron_)。 */
export function isCronSessionId(sessionId: string | undefined | null): boolean {
  return typeof sessionId === 'string' && sessionId.startsWith(CRON_SESSION_PREFIX);
}

/**
 * 从 cron 触发会话的 session_id 派生归属 job_id。
 * session_id 形如 `cron_<hex_ts>_<job_id>`;在已知 job id 列表里找后缀匹配。
 * 非 cron 会话 / 无匹配 → null。
 */
export function findJobIdFromCronSessionId(sessionId: string | undefined | null, jobIds: readonly string[]): string | null {
  if (!isCronSessionId(sessionId)) return null;
  const sid = sessionId as string;
  for (const id of jobIds) {
    if (id && sid.endsWith(`_${id}`)) return id;
  }
  return null;
}
