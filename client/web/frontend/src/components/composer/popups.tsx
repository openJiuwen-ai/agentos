/**
 * Composer 弹出层族：
 *  - PlusMenu        加号菜单（文件/模式/技能/专家/连接器，连接器含悬浮子菜单）
 *  - ModelSelector   模型选择（models.list 数据，Auto=默认模型）
 *  - PermissionSelector 权限选择（默认权限/完全访问权限，完全访问需确认）
 *  - SkillSelector   技能选择（skills.list）
 *  - ProjectSelector 项目空间选择（含新建项目）
 */
import { useEffect, useRef, useState } from 'react';
import { RefreshCcw, Box, Users, ChevronRight, ShieldAlert, ShieldCheck, Target } from 'lucide-react';
import autoModelIcon from '../../assets/design/home/auto-select-model.svg';
import defaultPermIcon from '../../assets/design/home/default-permission.svg';
import fullAccessIcon from '../../assets/design/home/full-access.svg';
import requestPermIcon from '../../assets/design/home/request-permission.svg';
import chevronDownIcon from '../../assets/design/home/chevron-down.svg';
import plusIcon from '../../assets/design/home/plus.svg';
import fileIcon from '../../assets/design/home/add-file.svg';
import skillIcon from '../../assets/design/home/skill.svg';
import connectorIcon from '../../assets/design/home/connector.svg';
import clockIcon from '../../assets/design/home/scheduled-task.svg';
import checkIcon from '../../assets/design/home/check.svg';
import closeIcon from '../../assets/design/home/close.svg';
import { Popup } from '../common/Popup';
import { CreateProjectDialog } from '../project/CreateProjectDialog';
import { NewProjectIcon, ProjectChevronDownIcon, ProjectSpaceIcon } from '../project/projectIcons';
import { useSessionStore, useWorkspaceStore } from '../../stores';
import { getProjectDisplayName } from '../../stores/workspaceStore';
import { useCreateProjectFlow } from '../../features/workspace/useCreateProjectFlow';
import { webRequest } from '../../services/webClient';
import type { Permission } from '../../types';

/* ================= 加号菜单 ================= */

const CONNECTOR_ITEMS = ['飞书', '企业微信', 'Github', 'Obsidian', 'Notion', 'Figma', 'Microsoft PowerPoint', 'Microsoft Excel', 'Microsoft Word'];

export function PlusMenu({
  sessionId,
  goalArmed,
  onPickFiles,
  onSchedule,
  onToggleGoal,
  onOpenSkills,
}: {
  sessionId: string;
  goalArmed: boolean;
  onPickFiles: () => void;
  onSchedule: () => void;
  onToggleGoal: () => void;
  onOpenSkills: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [modeSubOpen, setModeSubOpen] = useState(false);
  const [connectorSubOpen, setConnectorSubOpen] = useState(false);
  const [comingSubOpen, setComingSubOpen] = useState(false);
  const anchorRef = useRef<HTMLButtonElement>(null);
  void sessionId;
  void onOpenSkills; // 技能入口暂为「敬请期待」占位，保留 prop 兼容调用方

  const close = () => {
    setOpen(false);
    setModeSubOpen(false);
    setConnectorSubOpen(false);
    setComingSubOpen(false);
  };

  return (
    <>
      <button ref={anchorRef} className={`composer-plus ${open ? 'is-open' : ''}`} title="更多操作" onClick={() => (open ? close() : setOpen(true))}>
        <img src={plusIcon} alt="" style={{ width: 24, height: 24 }} />
      </button>
      <Popup open={open} anchorRef={anchorRef} placement="top-start" offset={10} onClose={close}>
        <div className="menu-pop plus-menu">
          <button
            className="menu-item"
            onClick={() => {
              close();
              onPickFiles();
            }}
          >
            <span className="menu-item-icon">
              <img src={fileIcon} alt="" style={{ width: 15, height: 15 }} />
            </span>
            <span className="menu-item-label">文件</span>
          </button>
          <div
            className="menu-item has-sub"
            onMouseEnter={() => {
              setModeSubOpen(true);
              setConnectorSubOpen(false);
            }}
            onMouseLeave={() => setModeSubOpen(false)}
          >
            <span className="menu-item-icon">
              <RefreshCcw size={15} />
            </span>
            <span className="menu-item-label">模式</span>
            <span className="menu-item-extra">设置定时任务或目标</span>
            <ChevronRight size={13} className="menu-sub-arrow" />
            {modeSubOpen ? (
              <div className="menu-pop sub-menu">
                <button
                  className="menu-item"
                  onClick={() => {
                    close();
                    onSchedule();
                  }}
                >
                  <span className="menu-item-icon">
                    <img src={clockIcon} alt="" style={{ width: 14, height: 14 }} />
                  </span>
                  <span className="menu-item-label">定时任务</span>
                </button>
                <button
                  className="menu-item"
                  onClick={() => {
                    close();
                    onToggleGoal();
                  }}
                >
                  <span className="menu-item-icon">
                    <Target size={14} />
                  </span>
                  <span className="menu-item-label">{goalArmed ? '取消目标' : '目标'}</span>
                </button>
              </div>
            ) : null}
          </div>
          <div
            className="menu-item has-sub"
            onMouseEnter={() => { setComingSubOpen(true); setModeSubOpen(false); setConnectorSubOpen(false); }}
            onMouseLeave={() => setComingSubOpen(false)}
          >
            <span className="menu-item-icon">
              <img src={skillIcon} alt="" style={{ width: 15, height: 15 }} />
            </span>
            <span className="menu-item-label">技能</span>
            <ChevronRight size={13} className="menu-sub-arrow" />
            {comingSubOpen ? (
              <div className="menu-pop sub-menu">
                <div className="menu-coming">
                  <div className="menu-coming-title">敬请期待</div>
                  <div className="menu-coming-desc">该功能正在建设中，敬请期待</div>
                </div>
              </div>
            ) : null}
          </div>
          <div
            className="menu-item has-sub"
            onMouseEnter={() => { setComingSubOpen(true); setModeSubOpen(false); setConnectorSubOpen(false); }}
            onMouseLeave={() => setComingSubOpen(false)}
          >
            <span className="menu-item-icon"><Users size={15} /></span>
            <span className="menu-item-label">专家</span>
            <ChevronRight size={13} className="menu-sub-arrow" />
            {comingSubOpen ? (
              <div className="menu-pop sub-menu">
                <div className="menu-coming">
                  <div className="menu-coming-title">敬请期待</div>
                  <div className="menu-coming-desc">该功能正在建设中，敬请期待</div>
                </div>
              </div>
            ) : null}
          </div>
          <div
            className="menu-item has-sub"
            onMouseEnter={() => {
              setConnectorSubOpen(true);
              setModeSubOpen(false);
            }}
            onMouseLeave={() => setConnectorSubOpen(false)}
          >
            <span className="menu-item-icon">
              <img src={connectorIcon} alt="" style={{ width: 15, height: 15 }} />
            </span>
            <span className="menu-item-label">连接器</span>
            <ChevronRight size={13} className="menu-sub-arrow" />
            {connectorSubOpen ? (
              <div className="menu-pop sub-menu">
                {CONNECTOR_ITEMS.map(name => (
                  <button key={name} className="menu-item" disabled title="暂未配置">
                    <span className="menu-item-icon connector-dot" />
                    <span className="menu-item-label">{name}</span>
                  </button>
                ))}
                <div className="menu-sep" />
                <button className="menu-item" disabled title="暂未开放">
                  <span className="menu-item-icon">
                    <img src={plusIcon} alt="" style={{ width: 14, height: 14 }} />
                  </span>
                  <span className="menu-item-label">管理连接器</span>
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </Popup>
    </>
  );
}

/* ================= 模型选择 ================= */

export function ModelSelector({ sessionId }: { sessionId: string }) {
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLButtonElement>(null);
  const chatModels = useSessionStore(s => s.chatAvailableModels);
  const defaultModelName = useSessionStore(s => s.defaultModelName);
  const selectedModelName = useSessionStore(s => s.runtimes[sessionId]?.selectedModelName ?? null);
  const setSelectedModelName = useSessionStore(s => s.setSelectedModelName);
  const getEffectiveModelName = useSessionStore(s => s.getEffectiveModelName);

  const effective = getEffectiveModelName(sessionId);
  // 只有「未选择」时才是 Auto；手动选择了默认模型时如实显示模型名
  const isAuto = !selectedModelName;
  const display = isAuto ? 'Auto' : (selectedModelName ?? 'Auto');

  const handleSelect = (name: string) => {
    setSelectedModelName(sessionId, name);
    setOpen(false);
  };

  return (
    <>
      <button ref={anchorRef} className="composer-model" onClick={() => setOpen(v => !v)} title="选择模型">
        <img src={autoModelIcon} alt="" style={{ width: 16, height: 16 }} />
        {/* DSL: container(41px) wraps text + chevron with space-between */}
        <span className="composer-model-label">
          <span className="composer-model-name">{display}</span>
          <img src={chevronDownIcon} alt="" className={open ? 'rotate-180' : ''} style={{ width: 10, height: 10, marginTop: 3 }} />
        </span>
      </button>
      <Popup open={open} anchorRef={anchorRef} placement="bottom-end" offset={8} onClose={() => setOpen(false)}>
        <div className="menu-pop model-menu">
          <div className="menu-title">选择模型</div>
          <button className="menu-item" onClick={() => defaultModelName && handleSelect(defaultModelName)}>
            <span className="menu-item-icon">{isAuto ? <img src={checkIcon} alt="" style={{ width: 14, height: 14 }} /> : null}</span>
            <span className="menu-item-label">Auto</span>
            <span className="menu-item-extra">{defaultModelName ?? effective ?? ''}</span>
          </button>
          <div className="menu-sep" />
          {chatModels.map(m => {
            const name = m.alias || m.model_name;
            const checked = !isAuto && selectedModelName === name;
            return (
              <button key={name} className="menu-item" onClick={() => handleSelect(name)}>
                <span className="menu-item-icon">{checked ? <img src={checkIcon} alt="" style={{ width: 14, height: 14 }} /> : null}</span>
                <span className="menu-item-label">{name}</span>
                <span className="menu-item-extra">{m.alias ? m.model_name : ''}</span>
              </button>
            );
          })}
          {chatModels.length === 0 ? <div className="empty-hint">暂无可用模型</div> : null}
        </div>
      </Popup>
    </>
  );
}

/* ================= 权限选择 ================= */

export function PermissionSelector({
  permission,
  onChange,
  variant,
}: {
  permission: Permission;
  onChange: (permission: Permission) => void;
  variant?: 'home' | 'chat';
}) {
  const [open, setOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const anchorRef = useRef<HTMLButtonElement>(null);

  const handleSelect = (value: Permission) => {
    setOpen(false);
    if (value === permission) return;
    if (value === 'full_access') {
      setConfirmOpen(true);
    } else {
      onChange('default');
    }
  };

  return (
    <>
      <button ref={anchorRef} className="composer-chip" onClick={() => setOpen(v => !v)} title="权限设置">
        <img
          src={permission === 'full_access' ? fullAccessIcon : variant === 'home' ? requestPermIcon : defaultPermIcon}
          alt=""
          style={{ width: 15, height: 15 }}
        />
        <span>{permission === 'full_access' ? '完全访问权限' : variant === 'home' ? '请求权限' : '默认权限'}</span>
        {variant !== 'home' ? <img src={chevronDownIcon} alt="" className={open ? 'rotate-180' : ''} style={{ width: 10, height: 10 }} /> : null}
      </button>
      <Popup open={open} anchorRef={anchorRef} placement="bottom-start" offset={8} onClose={() => setOpen(false)}>
        <div className="menu-pop">
          <button className="menu-item" onClick={() => handleSelect('default')}>
            <span className="menu-item-icon">
              {permission === 'default' ? <img src={checkIcon} alt="" style={{ width: 14, height: 14 }} /> : <ShieldCheck size={14} />}
            </span>
            <span className="menu-item-label">默认权限</span>
            <span className="menu-item-extra">敏感操作需确认</span>
          </button>
          <button className="menu-item" onClick={() => handleSelect('full_access')}>
            <span className="menu-item-icon">
              {permission === 'full_access' ? <img src={checkIcon} alt="" style={{ width: 14, height: 14 }} /> : <ShieldAlert size={14} />}
            </span>
            <span className="menu-item-label">完全访问权限</span>
            <span className="menu-item-extra">不再逐项确认</span>
          </button>
        </div>
      </Popup>
      {confirmOpen ? (
        <div className="modal-mask" onClick={() => setConfirmOpen(false)}>
          <div className="modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <div className="modal-title">开启完全访问权限？</div>
              <button className="icon-btn icon-btn--sm" onClick={() => setConfirmOpen(false)}>
                <img src={closeIcon} alt="" style={{ width: 16, height: 16 }} />
              </button>
            </div>
            <div className="modal-body">
              <p style={{ margin: 0, color: 'var(--t2)', lineHeight: 1.7 }}>
                开启后，智能体执行文件修改、命令运行等敏感操作时将不再逐项请求确认。请确认你信任当前任务内容。
              </p>
            </div>
            <div className="modal-foot">
              <button className="btn btn-ghost" onClick={() => setConfirmOpen(false)}>
                取消
              </button>
              <button
                className="btn btn-dark"
                onClick={() => {
                  setConfirmOpen(false);
                  onChange('full_access');
                }}
              >
                确认开启
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}

/* ================= 技能选择 ================= */

interface SkillItem {
  name: string;
  display_name?: string;
  enabled?: boolean;
  installed?: boolean;
  description?: string;
}

export function SkillSelector({
  sessionId,
  open,
  onClose,
  anchorRef,
}: {
  sessionId: string;
  open: boolean;
  onClose: () => void;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
}) {
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const selectedSkills = useSessionStore(s => s.runtimes[sessionId]?.selectedSkills ?? []);
  const addSelectedSkill = useSessionStore(s => s.addSelectedSkill);
  const removeSelectedSkill = useSessionStore(s => s.removeSelectedSkill);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    webRequest<{ skills?: SkillItem[] }>('skills.list', { with_installed: true }, { timeoutMs: 30_000 })
      .then(data => {
        setSkills((data.skills ?? []).filter(s => s.installed !== false && s.enabled !== false));
      })
      .catch(() => setSkills([]))
      .finally(() => setLoading(false));
  }, [open]);

  const filtered = query.trim() ? skills.filter(s => (s.display_name || s.name).toLowerCase().includes(query.trim().toLowerCase())) : skills;

  return (
    <Popup open={open} anchorRef={anchorRef} placement="top-start" offset={10} onClose={onClose}>
      <div className="menu-pop skill-menu">
        <div className="skill-menu-search">
          <input autoFocus placeholder="搜索技能…" value={query} onChange={e => setQuery(e.target.value)} />
        </div>
        <div className="skill-menu-list">
          {loading ? <div className="empty-hint">加载中…</div> : null}
          {!loading && filtered.length === 0 ? <div className="empty-hint">暂无可用技能</div> : null}
          {!loading &&
            filtered.map(skill => {
              const name = skill.name;
              const selected = selectedSkills.includes(name);
              return (
                <button
                  key={name}
                  className={`menu-item ${selected ? 'is-checked' : ''}`}
                  onClick={() => (selected ? removeSelectedSkill(sessionId, name) : addSelectedSkill(sessionId, name))}
                >
                  <span className="menu-item-icon">
                    <Box size={14} />
                  </span>
                  <span className="menu-item-label">{skill.display_name || name}</span>
                  {selected ? <img src={checkIcon} alt="" className="skill-check" style={{ width: 14, height: 14 }} /> : null}
                </button>
              );
            })}
        </div>
      </div>
    </Popup>
  );
}

/* ================= 项目空间选择 ================= */

export function ProjectSelector({ variant }: { variant?: 'home' | 'chat' }) {
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLButtonElement>(null);
  const projects = useWorkspaceStore(s => s.projects);
  const selectedProject = useWorkspaceStore(s => s.selectedProject);
  const setSelectedProject = useWorkspaceStore(s => s.setSelectedProject);
  const workMode = useWorkspaceStore(s => s.workMode);
  const {
    open: createOpen,
    submitting: createSubmitting,
    error: createError,
    openDialog: openCreateDialog,
    closeDialog: closeCreateDialog,
    submit: submitCreate,
  } = useCreateProjectFlow();

  const visibleProjects = projects.filter(p => !p.hidden && (p.work_mode ?? workMode) === workMode);

  return (
    <>
      <button ref={anchorRef} className="composer-chip" onClick={() => setOpen(v => !v)} title="选择项目空间">
        <ProjectSpaceIcon size={14} />
        <span>{selectedProject ? getProjectDisplayName(selectedProject) : '选择项目空间'}</span>
        {variant !== 'home' ? <ProjectChevronDownIcon size={10} className={open ? 'rotate-180' : ''} /> : null}
      </button>
      <Popup open={open} anchorRef={anchorRef} placement="bottom-start" offset={8} onClose={() => setOpen(false)}>
        <div className="menu-pop project-menu">
          <div className="menu-title">项目空间</div>
          <button
            className="menu-item"
            onClick={() => {
              setSelectedProject(null);
              setOpen(false);
            }}
          >
            <span className="menu-item-icon">{!selectedProject ? <img src={checkIcon} alt="" style={{ width: 14, height: 14 }} /> : null}</span>
            <span className="menu-item-label">默认工作区</span>
          </button>
          {visibleProjects.map(project => {
            const checked = selectedProject?.project_id === project.project_id;
            return (
              <button
                key={project.project_id}
                className="menu-item"
                onClick={() => {
                  setSelectedProject(project);
                  setOpen(false);
                }}
              >
                <span className="menu-item-icon">
                  {checked ? <img src={checkIcon} alt="" style={{ width: 14, height: 14 }} /> : <ProjectSpaceIcon size={14} />}
                </span>
                <span className="menu-item-label">{getProjectDisplayName(project)}</span>
              </button>
            );
          })}
          <div className="menu-sep" />
          <button
            className="menu-item"
            onClick={() => {
              setOpen(false);
              openCreateDialog();
            }}
          >
            <span className="menu-item-icon">
              <NewProjectIcon size={14} />
            </span>
            <span className="menu-item-label">新建项目</span>
          </button>
        </div>
      </Popup>

      <CreateProjectDialog open={createOpen} error={createError} submitting={createSubmitting} onCancel={closeCreateDialog} onSubmit={submitCreate} />
    </>
  );
}
