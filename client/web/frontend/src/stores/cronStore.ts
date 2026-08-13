import { create } from 'zustand';
import { webRequest } from '../services/webClient';
import { projectRegistryClient } from '../features/workspace/projectRegistryClient';
import type { CronJobDTO, CronJobPatch, CronPreviewItem, CronTemplateUI, FilterKind, Session, ViewMode } from '../types';
import { CRON_TEMPLATES } from '../utils/cronTemplates';

export interface SidebarCronJob {
  id: string;
  name: string;
  enabled: boolean;
  expired?: boolean;
  cron_expr: string;
  project_id: string;
  session_id?: string;
  // 推送频道 ID,字符串或逗号分隔的多个(对齐后端 CronJob.to_dict().targets);空串按后端默认 web
  targets?: string;
  created_at: number | string | null;
  updated_at: number | string | null;
}

/** 判断 cron job 的 targets 是否含 "web"(空串按后端 normalize 默认 web 处理) */
export function isWebChannelJob(targets?: string): boolean {
  const s = (targets ?? '').trim();
  if (!s) return true;
  return s.split(',').some(p => p.trim().toLowerCase() === 'web');
}

interface CronState {
  jobs: SidebarCronJob[];
  isLoading: boolean;
  expandedCronGroups: Record<string, boolean>;
  // cron_id → 触发会话列表
  cronSessions: Record<string, Session[]>;
  // cron_id → 加载中状态
  cronSessionsLoading: Record<string, boolean>;
  // job_id → 最近"立即执行"返回的 session_id，用于广播消息路由
  lastRunSessionId: Record<string, string>;
  setLastRunSessionId: (jobId: string, sessionId: string) => void;
  // 定时任务未读状态（is_placeholder=false 的广播到达时标记，点击后清除）
  unreadCronJobs: Record<string, boolean>;
  markCronJobUnread: (jobId: string) => void;
  clearCronJobUnread: (jobId: string) => void;
  loadJobs: () => Promise<void>;
  reload: () => Promise<void>;
  toggleCronGroup: (groupId: string) => void;
  loadCronSessions: (projectId: string, cronId: string) => Promise<void>;
  isCronGroupExpanded: (groupId: string) => boolean;
  // ---- Phase 0 新增:列表/筛选/视图状态 ----
  filter: FilterKind;
  searchKeyword: string;
  viewMode: ViewMode;
  templates: CronTemplateUI[];
  setFilter: (filter: FilterKind) => void;
  setSearchKeyword: (keyword: string) => void;
  setViewMode: (mode: ViewMode) => void;
  // ---- Phase 0 新增:RPC action(对齐后端 cron.job.get/update/preview)----
  getJob: (id: string) => Promise<CronJobDTO | null>;
  updateJob: (id: string, patch: CronJobPatch) => Promise<void>;
  previewJob: (id: string, count?: number) => Promise<CronPreviewItem[]>;
}

// 将未读状态持久化到 localStorage，用 queueMicrotask 延迟到当前同步热路径之后执行，
// 避免阻塞 WebSocket 消息处理；try/catch 防止配额满/隐私模式导致异常影响 store 状态
function persistCronUnread(state: Record<string, boolean>) {
  queueMicrotask(() => {
    try {
      localStorage.setItem('jiuwenswarm_cron_unread', JSON.stringify(state));
    } catch {
      /* ignore */
    }
  });
}

export const useCronStore = create<CronState>((set, get) => ({
  jobs: [],
  isLoading: false,
  expandedCronGroups: {},
  cronSessions: {},
  cronSessionsLoading: {},
  lastRunSessionId: {},
  setLastRunSessionId: (jobId, sessionId) => set(s => ({ lastRunSessionId: { ...s.lastRunSessionId, [jobId]: sessionId } })),
  unreadCronJobs: (() => {
    try {
      const value = JSON.parse(localStorage.getItem('jiuwenswarm_cron_unread') || '{}');
      return typeof value === 'object' && value !== null ? (value as Record<string, boolean>) : {};
    } catch {
      return {};
    }
  })(),
  markCronJobUnread: jobId => {
    set(s => {
      if (s.unreadCronJobs[jobId]) return s;
      const next = { ...s.unreadCronJobs, [jobId]: true };
      persistCronUnread(next);
      return { unreadCronJobs: next };
    });
  },
  clearCronJobUnread: jobId => {
    set(s => {
      if (!s.unreadCronJobs[jobId]) return s;
      const next = { ...s.unreadCronJobs };
      delete next[jobId];
      persistCronUnread(next);
      return { unreadCronJobs: next };
    });
  },

  loadJobs: async () => {
    set({ isLoading: true });
    try {
      const payload = await webRequest<{ jobs: SidebarCronJob[] }>('cron.job.list');
      // 侧边栏是 Web 端工作区,只展示 targets 含 "web" 的定时任务
      const webJobs = (payload.jobs || []).filter(j => isWebChannelJob(j.targets));
      set({ jobs: webJobs, isLoading: false });
    } catch {
      set({ jobs: [], isLoading: false });
    }
  },

  reload: async () => {
    await get().loadJobs();
  },

  toggleCronGroup: (groupId: string) => {
    set(state => ({
      expandedCronGroups: {
        ...state.expandedCronGroups,
        [groupId]: !state.expandedCronGroups[groupId],
      },
    }));
  },

  isCronGroupExpanded: (groupId: string) => {
    return get().expandedCronGroups[groupId] ?? false;
  },

  loadCronSessions: async (projectId: string, cronId: string) => {
    set(state => ({
      cronSessionsLoading: { ...state.cronSessionsLoading, [cronId]: true },
    }));
    try {
      const payload = await projectRegistryClient.getCronSessions(projectId, cronId);
      set(state => ({
        cronSessions: {
          ...state.cronSessions,
          [cronId]: payload.sessions || [],
        },
        cronSessionsLoading: { ...state.cronSessionsLoading, [cronId]: false },
      }));
    } catch {
      set(state => ({
        cronSessionsLoading: { ...state.cronSessionsLoading, [cronId]: false },
      }));
    }
  },

  // ---- Phase 0 新增:列表/筛选/视图状态 + RPC action ----
  filter: 'all',
  searchKeyword: '',
  viewMode: 'grid',
  templates: CRON_TEMPLATES as CronTemplateUI[],
  setFilter: filter => set({ filter }),
  setSearchKeyword: searchKeyword => set({ searchKeyword }),
  setViewMode: viewMode => set({ viewMode }),
  getJob: async id => {
    const payload = await webRequest<{ job: CronJobDTO }>('cron.job.get', { id });
    return payload?.job ?? null;
  },
  updateJob: async (id, patch) => {
    await webRequest<{ job: CronJobDTO }>('cron.job.update', { id, patch });
    // 后端无 CRUD 推送事件,本地 mutate 后刷新列表
    await get().loadJobs();
  },
  previewJob: async (id, count = 3) => {
    const payload = await webRequest<{ next: CronPreviewItem[] }>('cron.job.preview', {
      id,
      count,
    });
    return payload?.next ?? [];
  },
}));

const DEFAULT_PROJECT_ID = 'default';

/** proactive 自动任务 id（与后端 proactive_cron_sync.PROACTIVE_JOB_ID 一致）。 */
export const PROACTIVE_AUTO_JOB_ID = 'proactive-tick-auto';

// 系统自动维护的 cron job id。这类 job 由配置开关自动创建/删除，
// 不创建会话、不给推送的会话打 cron_id——所以"触发的会话"列表恒空，在会话侧栏是个空壳。
// 从会话侧栏隐藏它（Cron 面板里仍可见可编辑 cron 表达式/时区），避免空壳 item 碍眼。
const SYSTEM_AUTO_JOB_IDS = new Set([PROACTIVE_AUTO_JOB_ID]);

export function isDefaultProjectId(projectId: string): boolean {
  return !projectId || projectId === DEFAULT_PROJECT_ID;
}

/** 按项目过滤定时任务（默认项目返回 project_id 为空的）；系统自动维护 job 不进会话侧栏。 */
export function filterJobsForProject(jobs: SidebarCronJob[], projectId: string): SidebarCronJob[] {
  const filtered = isDefaultProjectId(projectId)
    ? jobs.filter(job => isDefaultProjectId(job.project_id) && !SYSTEM_AUTO_JOB_IDS.has(job.id))
    : jobs.filter(job => job.project_id === projectId && !SYSTEM_AUTO_JOB_IDS.has(job.id));
  return filtered.sort((a, b) => {
    const au = typeof a.updated_at === 'number' ? a.updated_at : 0;
    const bu = typeof b.updated_at === 'number' ? b.updated_at : 0;
    return bu - au;
  });
}
