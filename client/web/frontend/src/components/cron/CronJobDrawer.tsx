/**
 * CronJobDrawer — 定时任务创建/编辑抽屉(右抽屉 600px)。对照设计稿"定时任务 - 创建"。
 *
 * 三态:create(空白)/ edit(载入既有 job)/ template(预填模板)。编辑态经 getJob + normalizeJobForEdit 初始化。
 * 只传最基本字段:任务名称 / 提示词(→ description,纯 textarea)/ 执行频率(ScheduleBuilder)/ 时区 / 启用开关。
 *
 * 精简回退轮:撤销 permission/附件/技能/模型/项目空间/生效日期区间 等丰富字段,
 * 与后端 store.create_job / controller.create_job 的最小字段集对齐(见 types/cron.ts)。
 *
 * 文案硬编码设计稿原文中文(不用 i18n,与原版 1:1)。
 */
import { useEffect, useState } from 'react';
import { useCronStore } from '../../stores';
import { webRequest } from '../../services/webClient';
import { DEFAULT_CRON_TARGET, DEFAULT_CRON_TIMEZONE, normalizeJobForEdit, validateCronExpr } from '../../utils/cronExpr';
import type { CronTemplateUI } from '../../types';
import { CronSvgIcon } from './cronSvgIcons';
import { ScheduleBuilder } from './schedule/ScheduleBuilder';
import './cronDrawer.css';

export type CronDrawerMode = 'create' | 'edit' | 'template';

/** 文案严格对齐设计稿"定时任务 - 创建"原文(中文)。 */
const TEXT = {
  titleCreate: '创建新的定时任务',
  titleEdit: '编辑',
  fieldName: '任务名称',
  fieldNamePh: '请输入',
  fieldPrompt: '提示词',
  fieldPromptPh: '请输入提示词',
  sectionSettings: '任务设置',
  sectionSchedule: '执行频率',
  labelModel: '大语言模型',
  labelProject: '项目空间',
  labelPermission: '权限',
  comingSoon: '敬请期待',
  enabled: '启用',
  cancel: '取消',
  submitCreate: '创建',
  submitSave: '保存',
  errName: '请输入任务名称',
  errCronEmpty: '请设置执行频率',
  errCronInvalid: 'Cron 表达式格式不正确',
  loading: '加载中…',
} as const;

interface DrawerForm {
  name: string;
  description: string;
  cronExpr: string;
  timezone: string;
  enabled: boolean;
  wakeOffsetSeconds: number;
}

function createForm(initialDescription?: string): DrawerForm {
  return {
    name: '',
    description: initialDescription ?? '',
    cronExpr: '0 9 * * *',
    timezone: DEFAULT_CRON_TIMEZONE,
    enabled: true,
    wakeOffsetSeconds: 0,
  };
}

function templateForm(template: CronTemplateUI): DrawerForm {
  return { ...createForm(), name: template.name, description: template.prompt, cronExpr: template.cronExpr };
}

export interface CronJobDrawerProps {
  mode: CronDrawerMode;
  editJobId?: string;
  template?: CronTemplateUI;
  /** create 模式:预填提示词(聊天框"+→定时任务"草稿流) */
  initialDescription?: string;
  onClose: () => void;
  /** 创建成功(已 reload + 高亮由父级处理) */
  onCreated: () => void;
  /** 保存成功 */
  onSaved: () => void;
  onToast: (message: string, isError?: boolean) => void;
}

export function CronJobDrawer({ mode, editJobId, template, initialDescription, onClose, onCreated, onSaved, onToast }: CronJobDrawerProps) {
  const getJob = useCronStore(s => s.getJob);
  const updateJob = useCronStore(s => s.updateJob);

  const [form, setForm] = useState<DrawerForm>(() => (mode === 'template' && template ? templateForm(template) : createForm(initialDescription)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [editLoading, setEditLoading] = useState(mode === 'edit');

  // 编辑态:载入完整 job(getJob 取 description/wake_offset 等列表缺失字段)
  useEffect(() => {
    if (mode !== 'edit' || !editJobId) {
      setEditLoading(false);
      return undefined;
    }
    let cancelled = false;
    void (async () => {
      try {
        const job = await getJob(editJobId);
        if (cancelled || !job) return;
        const edit = normalizeJobForEdit(job);
        setForm({
          name: edit.name,
          description: edit.description,
          cronExpr: edit.cron_expr || '0 9 * * *',
          timezone: edit.timezone || DEFAULT_CRON_TIMEZONE,
          enabled: edit.enabled,
          wakeOffsetSeconds: edit.wake_offset_seconds,
        });
      } catch {
        if (!cancelled) onToast('加载任务失败', true);
      } finally {
        if (!cancelled) setEditLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mode, editJobId, getJob, onToast]);

  const patch = (p: Partial<DrawerForm>) => setForm(f => ({ ...f, ...p }));

  // ESC 关闭
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [busy, onClose]);

  const isEdit = mode === 'edit';
  const title = isEdit ? TEXT.titleEdit : TEXT.titleCreate;
  const submitLabel = isEdit ? TEXT.submitSave : TEXT.submitCreate;

  const handleSubmit = async () => {
    setError('');
    const name = form.name.trim();
    if (!name) {
      setError(TEXT.errName);
      return;
    }
    const cronExpr = form.cronExpr.trim();
    if (!cronExpr) {
      setError(TEXT.errCronEmpty);
      return;
    }
    if (!validateCronExpr(cronExpr).valid) {
      setError(TEXT.errCronInvalid);
      return;
    }

    const baseFields = {
      name,
      description: form.description.trim(),
      cron_expr: cronExpr,
      timezone: form.timezone,
      targets: DEFAULT_CRON_TARGET,
      enabled: form.enabled,
      wake_offset_seconds: form.wakeOffsetSeconds,
    };

    setBusy(true);
    try {
      if (isEdit && editJobId) {
        await updateJob(editJobId, baseFields);
        onSaved();
      } else {
        await webRequest('cron.job.create', { ...baseFields, mode: 'agent' });
        onCreated();
      }
    } catch (e) {
      onToast(e instanceof Error ? `${isEdit ? '保存' : '创建'}失败：${e.message}` : `${isEdit ? '保存' : '创建'}失败`, true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="cron-drawer__overlay" onMouseDown={busy ? undefined : onClose}>
      <div className="cron-drawer" role="dialog" aria-modal="true" aria-label={title} onMouseDown={e => e.stopPropagation()}>
        <div className="cron-drawer__head">
          <div className="cron-drawer__title">{title}</div>
          <button type="button" className="cron-drawer__close" aria-label="关闭" onClick={onClose} disabled={busy}>
            <CronSvgIcon.close className="cron-drawer__close-icon" />
          </button>
        </div>

        {editLoading ? (
          <div className="cron-drawer__body">
            <div className="cron-sb__placeholder">{TEXT.loading}</div>
          </div>
        ) : (
          <>
            <div className="cron-drawer__body">
              <div className="cron-drawer__field">
                <label className="cron-drawer__label">{TEXT.fieldName}</label>
                <input
                  className="cron-drawer__input"
                  placeholder={TEXT.fieldNamePh}
                  value={form.name}
                  onChange={e => patch({ name: e.target.value })}
                  autoFocus
                />
              </div>

              {/* 提示词(纯 textarea → description);底部 "+" 附件图标(设计稿 22×22,功能待定→禁用) */}
              <div className="cron-drawer__field">
                <label className="cron-drawer__label">{TEXT.fieldPrompt}</label>
                <div className="cron-drawer__textarea-wrap">
                  <textarea
                    className="cron-drawer__textarea"
                    placeholder={TEXT.fieldPromptPh}
                    value={form.description}
                    onChange={e => patch({ description: e.target.value })}
                    rows={4}
                  />
                  <button type="button" className="cron-drawer__textarea-action" aria-label="附件" disabled>
                    <CronSvgIcon.plus className="cron-drawer__textarea-action-icon" />
                  </button>
                </div>
              </div>

              {/* 任务设置(决策④:大语言模型/项目空间/权限 后端无列 → 禁用 + "敬请期待" 纯视觉) */}
              <div className="cron-drawer__field">
                <span className="cron-drawer__label">{TEXT.sectionSettings}</span>
                <div className="cron-drawer__section">
                  <div className="cron-drawer__setting-row">
                    <span className="cron-drawer__setting-label">{TEXT.labelModel}</span>
                    <span className="cron-drawer__setting-value cron-drawer__setting-value--disabled">{TEXT.comingSoon}</span>
                  </div>
                  <div className="cron-drawer__setting-row">
                    <span className="cron-drawer__setting-label">{TEXT.labelProject}</span>
                    <span className="cron-drawer__setting-value cron-drawer__setting-value--disabled">{TEXT.comingSoon}</span>
                  </div>
                  <div className="cron-drawer__setting-row">
                    <span className="cron-drawer__setting-label">{TEXT.labelPermission}</span>
                    <span className="cron-drawer__setting-value cron-drawer__setting-value--disabled">{TEXT.comingSoon}</span>
                  </div>
                </div>
              </div>

              {/* 执行频率(带边框盒):ScheduleBuilder(执行周期/时间/生效日期区间/时区) */}
              <div className="cron-drawer__field">
                <span className="cron-drawer__label">{TEXT.sectionSchedule}</span>
                <div className="cron-drawer__section">
                  <ScheduleBuilder
                    initialCron={form.cronExpr}
                    onCronChange={expr => patch({ cronExpr: expr })}
                    timezone={form.timezone}
                    onTimezoneChange={tz => patch({ timezone: tz })}
                  />
                </div>
              </div>

              {/* 启用开关(编辑态有意义;create 默认启用) */}
              {isEdit ? (
                <div className="cron-drawer__field">
                  <span className="cron-drawer__label">{TEXT.enabled}</span>
                  <button
                    type="button"
                    className={`cron-toggle${form.enabled ? ' cron-toggle--on' : ''}`}
                    role="switch"
                    aria-checked={form.enabled}
                    aria-label={TEXT.enabled}
                    onClick={() => patch({ enabled: !form.enabled })}
                  >
                    <span className="cron-toggle__knob" />
                  </button>
                </div>
              ) : null}

              {error ? <div className="cron-drawer__error">{error}</div> : null}
            </div>

            <div className="cron-drawer__foot">
              <button type="button" className="cron-drawer__btn cron-drawer__btn--ghost" onClick={onClose} disabled={busy}>
                {TEXT.cancel}
              </button>
              <button type="button" className="cron-drawer__btn cron-drawer__btn--primary" disabled={busy} onClick={() => void handleSubmit()}>
                {busy ? '…' : submitLabel}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
