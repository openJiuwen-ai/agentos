/**
 * 定时任务面板 —— Phase 3 起渲染 CronHomePage + CronJobDrawer(创建/编辑/模板抽屉)。
 *
 * 本组件保留为 App.tsx 的挂载点,维持 props 契约(onToast/initialDraft/onConsumeDraft)
 * 与既有删除弹窗 + RPC 处理器。Phase 3 用 CronJobDrawer 替换原始创建弹窗:
 * CreateDropdown"手动创建"→ 抽屉 create;CronCard"编辑"→ 抽屉 edit;模板"使用"→ 抽屉 template。
 * 创建成功 → reload + 新卡高亮(2s 闪);保存成功 → reload。无 toast(设计还原)。
 *
 * Phase 4:执行历史数据范围 = 当前项目。projectId 取自 workspace selectedProject,空/未选 → 'default'。
 *           onOpenSession 经回调上抛 App.handleSelectSession(切到对话视图打开会话)。
 */
import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { useCronStore, useWorkspaceStore, type SidebarCronJob } from '../../stores';
import type { CronTemplateUI } from '../../types';
import { webRequest } from '../../services/webClient';
import { CronHomePage } from '../cron';
import { CronJobDrawer } from '../cron/CronJobDrawer';
import './CronPanel.css';

type DrawerState =
  | { mode: 'create'; initialDescription?: string }
  | { mode: 'edit'; editJobId: string }
  | { mode: 'template'; template: CronTemplateUI }
  | null;

const HIGHLIGHT_MS = 2500;
const FALLBACK_PROJECT_ID = 'default';

export function CronPanel({
  onToast,
  initialDraft,
  onConsumeDraft,
  onOpenSession,
  onCreateViaChat,
}: {
  onToast: (message: string, isError?: boolean) => void;
  initialDraft?: string;
  onConsumeDraft?: () => void;
  /** Phase 4:点击执行历史某条会话 → 切到对话视图打开(App.handleSelectSession) */
  onOpenSession: (sessionId: string) => void;
  /** 通过聊天创建:切到对话 + 预填引导文案,agent 用 cron_create_job 工具建任务(App 层路由) */
  onCreateViaChat: () => void;
}) {
  const jobs = useCronStore(s => s.jobs);
  const loadJobs = useCronStore(s => s.loadJobs);
  const selectedProject = useWorkspaceStore(s => s.selectedProject);
  // 执行历史数据范围:当前选中项目,空/未选 → 'default'(与 cronStore DEFAULT_PROJECT_ID 对齐)
  const projectId = selectedProject?.project_id || FALLBACK_PROJECT_ID;

  const [drawer, setDrawer] = useState<DrawerState>(null);
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<SidebarCronJob | null>(null);
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  // 聊天输入框「+ → 模式 → 定时任务」跳入:预填提示词并打开抽屉(create)
  useEffect(() => {
    if (initialDraft !== undefined) {
      setDrawer({ mode: 'create', initialDescription: initialDraft });
      onConsumeDraft?.();
    }
  }, [initialDraft, onConsumeDraft]);

  useEffect(
    () => () => {
      if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current);
    },
    []
  );

  const handleToggle = async (id: string) => {
    const job = jobs.find(j => j.id === id);
    if (!job) return;
    try {
      await webRequest('cron.job.toggle', { id, enabled: !job.enabled });
      await loadJobs();
    } catch (error) {
      onToast(error instanceof Error ? error.message : '操作失败', true);
    }
  };

  const handleRunNow = async (id: string) => {
    const job = jobs.find(j => j.id === id);
    try {
      await webRequest('cron.job.run_now', { id });
      onToast(`已触发「${job?.name ?? '任务'}」`);
    } catch (error) {
      onToast(error instanceof Error ? error.message : '触发失败', true);
    }
  };

  const handleDeleteRequest = (id: string) => {
    setDeleteTarget(jobs.find(j => j.id === id) ?? null);
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setBusy(true);
    try {
      await webRequest('cron.job.delete', { id: deleteTarget.id });
      onToast('已删除');
      setDeleteTarget(null);
      await loadJobs();
    } catch (error) {
      onToast(error instanceof Error ? error.message : '删除失败', true);
    } finally {
      setBusy(false);
    }
  };

  const handleViaChat = () => {
    // 切到对话 + 预填引导文案,让 agent 用 cron_create_job 工具建任务(App 层路由)
    onCreateViaChat();
  };

  // 抽屉创建成功:reload + diff 找到新 job → 高亮(无 toast,设计还原)
  const handleDrawerCreated = async () => {
    const before = new Set(useCronStore.getState().jobs.map(j => j.id));
    setDrawer(null);
    await loadJobs();
    const after = useCronStore.getState().jobs;
    const newJob = after.find(j => !before.has(j.id));
    if (newJob) {
      setHighlightId(newJob.id);
      if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current);
      highlightTimerRef.current = setTimeout(() => setHighlightId(null), HIGHLIGHT_MS);
    }
  };

  const handleDrawerSaved = async () => {
    setDrawer(null);
    await loadJobs();
  };

  return (
    <>
      <CronHomePage
        onToggle={handleToggle}
        onRunNow={handleRunNow}
        onDelete={handleDeleteRequest}
        onEdit={id => setDrawer({ mode: 'edit', editJobId: id })}
        onCreateManual={() => setDrawer({ mode: 'create' })}
        onUseTemplate={template => setDrawer({ mode: 'template', template })}
        onCreateViaChat={handleViaChat}
        projectId={projectId}
        onOpenSession={onOpenSession}
        highlightId={highlightId}
      />

      {drawer ? (
        <CronJobDrawer
          key={drawer.mode === 'edit' ? `edit-${drawer.editJobId}` : drawer.mode === 'template' ? `tpl-${drawer.template.id}` : 'create'}
          mode={drawer.mode}
          editJobId={drawer.mode === 'edit' ? drawer.editJobId : undefined}
          template={drawer.mode === 'template' ? drawer.template : undefined}
          initialDescription={drawer.mode === 'create' ? drawer.initialDescription : undefined}
          onClose={() => setDrawer(null)}
          onCreated={() => void handleDrawerCreated()}
          onSaved={() => void handleDrawerSaved()}
          onToast={onToast}
        />
      ) : null}

      {/* 删除确认 */}
      {deleteTarget ? (
        <div className="modal-mask" onClick={() => setDeleteTarget(null)}>
          <div className="modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <div className="modal-title">删除定时任务</div>
              <button className="icon-btn icon-btn--sm" onClick={() => setDeleteTarget(null)}>
                <X size={16} />
              </button>
            </div>
            <div className="modal-body">
              <p style={{ margin: 0, color: 'var(--t2)' }}>确定删除「{deleteTarget.name}」吗？此操作不可恢复。</p>
            </div>
            <div className="modal-foot">
              <button className="btn btn-ghost" onClick={() => setDeleteTarget(null)}>
                取消
              </button>
              <button className="btn btn-dark" disabled={busy} onClick={() => void handleDelete()}>
                {busy ? '删除中…' : '删除'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
