/**
 * 定时任务面板 —— cron.job.list/create/toggle/run_now/delete（仿 jiuwenswarm 触发方式）
 */
import { useEffect, useState } from 'react';
import { Clock, Plus, Play, Trash2, RefreshCw, X } from 'lucide-react';
import { useCronStore, type SidebarCronJob } from '../stores';
import { webRequest } from '../services/webClient';
import './CronPanel.css';

function formatCronTime(value: number | string | null): string {
  if (value == null) return '';
  const ms = typeof value === 'number' ? (value < 1e11 ? value * 1000 : value) : Date.parse(value);
  if (!Number.isFinite(ms)) return '';
  const d = new Date(ms);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

export function CronPanel({
  onToast,
  initialDraft,
  onConsumeDraft,
}: {
  onToast: (message: string, isError?: boolean) => void;
  initialDraft?: string;
  onConsumeDraft?: () => void;
}) {
  const jobs = useCronStore((s) => s.jobs);
  const isLoading = useCronStore((s) => s.isLoading);
  const loadJobs = useCronStore((s) => s.loadJobs);

  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState('');
  const [cronExpr, setCronExpr] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<SidebarCronJob | null>(null);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  // 从输入框「+ → 模式 → 定时任务」跳入：预填内容并打开创建弹窗
  useEffect(() => {
    if (initialDraft !== undefined) {
      setDescription(initialDraft);
      setCreateOpen(true);
      onConsumeDraft?.();
    }
  }, [initialDraft, onConsumeDraft]);

  const handleCreate = async () => {
    if (!name.trim()) { onToast('请输入任务名称', true); return; }
    if (!cronExpr.trim()) { onToast('请输入 cron 表达式', true); return; }
    if (!description.trim()) { onToast('请输入任务内容', true); return; }
    setBusy(true);
    try {
      await webRequest('cron.job.create', {
        name: name.trim(),
        description: description.trim(),
        cron_expr: cronExpr.trim(),
        timezone: 'Asia/Shanghai',
        targets: 'web',
        enabled: true,
        wake_offset_seconds: 0,
        project_dir: '',
        mode: 'agent',
      });
      onToast('定时任务已创建');
      setCreateOpen(false);
      setName('');
      setCronExpr('');
      setDescription('');
      await loadJobs();
    } catch (error) {
      onToast(error instanceof Error ? `创建失败：${error.message}` : '创建失败', true);
    } finally {
      setBusy(false);
    }
  };

  const handleToggle = async (job: SidebarCronJob) => {
    try {
      await webRequest('cron.job.toggle', { id: job.id, enabled: !job.enabled });
      await loadJobs();
    } catch (error) {
      onToast(error instanceof Error ? error.message : '操作失败', true);
    }
  };

  const handleRunNow = async (job: SidebarCronJob) => {
    try {
      await webRequest('cron.job.run_now', { id: job.id });
      onToast(`已触发「${job.name}」`);
    } catch (error) {
      onToast(error instanceof Error ? error.message : '触发失败', true);
    }
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

  return (
    <div className="cron-page">
      <div className="cron-head">
        <div className="cron-title">
          <Clock size={18} />
          <span>定时任务</span>
        </div>
        <div className="cron-head-actions">
          <button className="icon-btn" title="刷新" onClick={() => void loadJobs()}>
            <RefreshCw size={16} className={isLoading ? 'spin' : ''} />
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => setCreateOpen(true)}>
            <Plus size={14} /> 新建任务
          </button>
        </div>
      </div>

      <div className="cron-body">
        {jobs.length === 0 && !isLoading ? (
          <div className="cron-empty">
            <Clock size={36} className="cron-empty-icon" />
            <div>暂无定时任务</div>
            <div className="cron-empty-sub">创建任务后，智能体将在指定时间自动执行</div>
          </div>
        ) : (
          <div className="cron-list">
            {jobs.map((job) => (
              <div key={job.id} className="cron-item">
                <div className="cron-item-main">
                  <div className="cron-item-name">
                    {job.name}
                    {job.expired ? <span className="cron-badge cron-badge--expired">已过期</span> : null}
                  </div>
                  <div className="cron-item-expr">{job.cron_expr}</div>
                  <div className="cron-item-time">更新于 {formatCronTime(job.updated_at)}</div>
                </div>
                <div className="cron-item-actions">
                  <button className="btn btn-ghost btn-sm" onClick={() => void handleRunNow(job)}>
                    <Play size={12} /> 立即执行
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={() => void handleToggle(job)}>
                    {job.enabled ? '暂停' : '启用'}
                  </button>
                  <button className="icon-btn icon-btn--sm cron-delete" title="删除" onClick={() => setDeleteTarget(job)}>
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 新建弹窗 */}
      {createOpen ? (
        <div className="modal-mask" onClick={() => setCreateOpen(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div className="modal-title">新建定时任务</div>
              <button className="icon-btn icon-btn--sm" onClick={() => setCreateOpen(false)}><X size={16} /></button>
            </div>
            <div className="modal-body cron-form">
              <label className="cron-label">任务名称</label>
              <input className="form-input" placeholder="例如：每日晨会纪要" value={name} onChange={(e) => setName(e.target.value)} />
              <label className="cron-label">cron 表达式</label>
              <input className="form-input" placeholder="例如：0 9 * * *（每天 9:00）" value={cronExpr} onChange={(e) => setCronExpr(e.target.value)} />
              <label className="cron-label">任务内容</label>
              <textarea
                className="form-input cron-textarea"
                placeholder="到时间后希望智能体执行的内容…"
                rows={4}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
            <div className="modal-foot">
              <button className="btn btn-ghost" onClick={() => setCreateOpen(false)}>取消</button>
              <button className="btn btn-primary" disabled={busy} onClick={() => void handleCreate()}>
                {busy ? '创建中…' : '创建'}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* 删除确认 */}
      {deleteTarget ? (
        <div className="modal-mask" onClick={() => setDeleteTarget(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div className="modal-title">删除定时任务</div>
            </div>
            <div className="modal-body">
              <p style={{ margin: 0, color: 'var(--t2)' }}>确定删除「{deleteTarget.name}」吗？此操作不可恢复。</p>
            </div>
            <div className="modal-foot">
              <button className="btn btn-ghost" onClick={() => setDeleteTarget(null)}>取消</button>
              <button className="btn btn-dark" disabled={busy} onClick={() => void handleDelete()}>
                {busy ? '删除中…' : '删除'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
