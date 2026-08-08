/**
 * CronHistoryList — 执行历史 tab(Phase 4 真实化 + Phase 5 job 归属)。
 *
 * 替换 Phase 2 的"即将上线"占位:渲染当前项目下 cron 触发的会话扁平列表,
 * 按最近活动时间倒序(newest first)。每行:[job 名·]标题 + 状态 Chip + 时间 + 消息数;点击整行打开会话。
 *
 * 数据通路:projectRegistryClient.getCronSessions(projectId)(不传 cronId → 整项目 cron 会话)。
 *   注:cronStore.loadCronSessions 强制 cronId 且按 cronId 落 store(为侧栏 per-job 展开用);
 *   执行历史是项目级扁平视图,故直接调 client(展示层数据获取,与 CronHomePage 直接调
 *   getJob/previewJob 同构),不改 store 数据层。
 *
 * Phase 5 job 归属:Session 无 cron_id 字段,但后端 cron 触发的会话 session_id = `cron_<ts>_<job_id>`
 * (scheduler.py:441)。前端经 findJobIdFromCronSessionId 解析 session_id 后缀 + cronStore jobs
 * 派生归属 job,行内前置「job 名 · 」(无后端改动)。
 *
 * 数据适配:
 *   - 时间:优先 last_message_at(Unix 秒),回退 updated_at(ISO);均经 formatCronDateTime。
 *   - 加载失败:client 抛错 → 回退空态(不弹错误窗)。
 *
 * 文案硬编码合理中文(执行历史无设计稿原文,不用 i18n)。
 */
import { useEffect, useMemo, useState } from 'react';
import type { Session } from '../../types';
import { projectRegistryClient } from '../../features/workspace/projectRegistryClient';
import { useCronStore } from '../../stores';
import { formatCronDateTime } from '../../utils/cronLabel';
import { sessionStatusToLabel } from '../../utils/sessionStatus';
import { findJobIdFromCronSessionId } from '../../utils/cronSessionId';
import { Chip } from './Chip';

const TEXT = {
  loading: '加载中…',
  empty: '暂无执行记录',
  emptyHint: '定时任务触发后,执行记录将显示在此处',
  untitled: '未命名会话',
} as const;

/** 会话排序键(Unix 秒):优先 last_message_at,回退 updated_at 解析。 */
function sessionSortValue(s: Session): number {
  if (typeof s.last_message_at === 'number' && s.last_message_at > 0) return s.last_message_at;
  const parsed = Date.parse(s.updated_at || '');
  return Number.isFinite(parsed) ? parsed / 1000 : 0;
}

/** 会话展示时间:优先 last_message_at,回退 updated_at;均经 formatCronDateTime 格式化。 */
function formatSessionTime(s: Session): string {
  if (typeof s.last_message_at === 'number' && s.last_message_at > 0) {
    return formatCronDateTime(s.last_message_at);
  }
  return formatCronDateTime(s.updated_at || null);
}

export interface CronHistoryListProps {
  /** 当前项目 id(空/默认项目 → 'default');CronPanel 从 workspace selectedProject 取并兜底 */
  projectId: string;
  /** 点击某条会话 → 打开(经 CronPanel → App.handleSelectSession 切到对话视图) */
  onOpenSession: (sessionId: string) => void;
}

export function CronHistoryList({ projectId, onOpenSession }: CronHistoryListProps) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const jobs = useCronStore(s => s.jobs);
  const jobIds = useMemo(() => jobs.map(j => j.id), [jobs]);

  // Phase 5:session_id → 归属 job 名(cron_<ts>_<job_id> 后缀派生)
  const jobNameBySession = useMemo(() => {
    const m = new Map<string, string>();
    for (const s of sessions) {
      const jid = findJobIdFromCronSessionId(s.session_id, jobIds);
      if (!jid) continue;
      const job = jobs.find(j => j.id === jid);
      if (job) m.set(s.session_id, job.name);
    }
    return m;
  }, [sessions, jobIds, jobs]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const payload = await projectRegistryClient.getCronSessions(projectId);
        if (cancelled) return;
        const sorted = [...(payload.sessions || [])].sort((a, b) => sessionSortValue(b) - sessionSortValue(a));
        setSessions(sorted);
      } catch {
        if (!cancelled) setSessions([]);
      } finally {
        if (!cancelled) {
          setLoading(false);
          setLoaded(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  if (loading) {
    return <div className="cron-history-loading">{TEXT.loading}</div>;
  }

  if (loaded && sessions.length === 0) {
    return (
      <div className="cron-history-empty">
        <div className="cron-history-empty__text">{TEXT.empty}</div>
        <div className="cron-history-empty__hint">{TEXT.emptyHint}</div>
      </div>
    );
  }

  return (
    <div className="cron-history-list">
      {sessions.map(s => {
        const jobName = jobNameBySession.get(s.session_id);
        const title = s.display_title || s.title || TEXT.untitled;
        return (
          <button key={s.session_id} type="button" className="cron-history-row" onClick={() => onOpenSession(s.session_id)}>
            <div className="cron-history-row__title">{jobName ? `${jobName} · ${title}` : title}</div>
            <div className="cron-history-row__meta">
              <Chip label={sessionStatusToLabel(s.status)} />
              <span className="cron-history-row__time">{formatSessionTime(s)}</span>
              <span className="cron-history-row__count">{s.message_count ?? 0} 条消息</span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
