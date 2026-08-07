/**
 * 侧边栏 —— 按 UI_design/对话-首页 设计稿实现
 * 结构：Logo 头部 / 新建对话·定时任务·插件·更多 / 项目列表（可展开会话 + 更多操作）/ 对话列表 / 底部用户区
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  SquarePen, Clock, LayoutGrid, MoreHorizontal, Search, PanelLeftClose, PanelLeftOpen,
  Pin, Pencil, Trash2, Ellipsis, Settings, LogOut, Wrench, Loader2,
  MessageSquare, ChevronRight,
} from 'lucide-react';
import type { Session } from '../../types';
import type { ProjectInfo } from '../../features/workspace/projectTypes';
import { useChatStore, useSessionStore, useWorkspaceStore } from '../../stores';
import { getProjectDisplayName, isDefaultProject } from '../../stores/workspaceStore';
import { useCreateProjectFlow } from '../../features/workspace/useCreateProjectFlow';
import { sortSessionsForSidebar, getSessionIndicator } from '../../multi-session/sidebar/sidebarModel';
import { Popup } from '../common/Popup';
import { CreateProjectDialog } from '../project/CreateProjectDialog';
import {
  NewProjectIcon,
  ProjectChevronDownIcon,
  ProjectSpaceIcon,
} from '../project/projectIcons';
import { ProjectSectionHeader } from './ProjectSectionHeader';
import './Sidebar.css';

export interface SidebarProps {
  username: string;
  activeSessionId: string | null;
  activeNav: 'chat' | 'cron';
  collapsed: boolean;
  onToggleCollapse: () => void;
  onNewChat: () => void;
  onOpenCron: () => void;
  onOpenPlugins: () => void;
  onOpenTools: () => void;
  onOpenSettings: () => void;
  onLogout: () => void;
  onSelectSession: (sessionId: string) => void;
  onRenameSession: (session: Session) => void;
  onDeleteSession: (session: Session) => void;
}

function LogoMark() {
  return (
    <div className="sidebar-logo" aria-hidden="true">
      <svg width="18" height="18" viewBox="0 0 34 34" fill="none">
        <path d="M17 3L28.5 9.6v13.2L17 31 5.5 22.8V9.6L17 3Z" stroke="#fff" strokeWidth="2.4" strokeLinejoin="round" />
        <circle cx="17" cy="14.5" r="3.2" fill="#fff" />
        <path d="M9.5 24.5c2-3.6 4.7-5.4 7.5-5.4s5.5 1.8 7.5 5.4" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" />
      </svg>
    </div>
  );
}

function formatTime(timestamp?: number | string): string {
  let ms: number | null = null;
  if (typeof timestamp === 'number') ms = timestamp < 1e11 ? timestamp * 1000 : timestamp;
  else if (typeof timestamp === 'string') { const p = Date.parse(timestamp); ms = Number.isNaN(p) ? null : p; }
  if (!ms) return '';
  const date = new Date(ms);
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  if (sameDay) return date.toTimeString().slice(0, 5);
  const diff = now.getTime() - ms;
  if (diff < 7 * 86400_000) return `${Math.max(1, Math.floor(diff / 86400_000))}天前`;
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

export function Sidebar({
  username, activeSessionId, activeNav, collapsed, onToggleCollapse,
  onNewChat, onOpenCron, onOpenPlugins, onOpenTools, onOpenSettings, onLogout,
  onSelectSession, onRenameSession, onDeleteSession,
}: SidebarProps) {
  const { t } = useTranslation();
  const sessions = useSessionStore((s) => s.sessions);
  const projects = useWorkspaceStore((s) => s.projects);
  const projectSessions = useWorkspaceStore((s) => s.projectSessions);
  const pinnedSessions = useWorkspaceStore((s) => s.pinnedSessions);
  const loadProjectSessions = useWorkspaceStore((s) => s.loadProjectSessions);
  const expandedProjectIds = useWorkspaceStore((s) => s.expandedProjectIds);
  const toggleProjectExpanded = useWorkspaceStore((s) => s.toggleProjectExpanded);
  const selectedProject = useWorkspaceStore((s) => s.selectedProject);
  const setSelectedProject = useWorkspaceStore((s) => s.setSelectedProject);
  const workMode = useWorkspaceStore((s) => s.workMode);
  const pinSession = useWorkspaceStore((s) => s.pinSession);
  const pinProject = useWorkspaceStore((s) => s.pinProject);
  const renameProject = useWorkspaceStore((s) => s.renameProject);
  const removeProject = useWorkspaceStore((s) => s.removeProject);
  const chatRuntimes = useChatStore((s) => s.runtimes);
  const {
    open: createProjectOpen,
    submitting: createProjectSubmitting,
    error: createProjectError,
    openDialog: openCreateProject,
    closeDialog: closeCreateProject,
    submit: handleCreateProject,
  } = useCreateProjectFlow();

  const [sessionMenuId, setSessionMenuId] = useState<string | null>(null);
  const [projectMenuId, setProjectMenuId] = useState<string | null>(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [renameProjectTarget, setRenameProjectTarget] = useState<ProjectInfo | null>(null);
  const [renameProjectValue, setRenameProjectValue] = useState('');
  const [renameProjectError, setRenameProjectError] = useState<string | null>(null);
  const [renameProjectBusy, setRenameProjectBusy] = useState(false);
  const [deleteProjectTarget, setDeleteProjectTarget] = useState<ProjectInfo | null>(null);
  const [deleteProjectError, setDeleteProjectError] = useState<string | null>(null);
  const [deleteProjectBusy, setDeleteProjectBusy] = useState(false);
  const sessionMenuAnchorRef = useRef<HTMLButtonElement | null>(null);
  const projectMenuAnchorRef = useRef<HTMLButtonElement | null>(null);
  const userMenuAnchorRef = useRef<HTMLButtonElement | null>(null);
  const moreMenuAnchorRef = useRef<HTMLButtonElement | null>(null);

  const visibleProjects = useMemo(() => {
    const list = projects.filter((p) => !p.hidden && (p.work_mode ?? workMode) === workMode);
    return [...list].sort((a, b) => {
      const pinDelta = Number(Boolean(b.pinned && !isDefaultProject(b))) - Number(Boolean(a.pinned && !isDefaultProject(a)));
      if (pinDelta !== 0) return pinDelta;
      return getProjectDisplayName(a).localeCompare(getProjectDisplayName(b), 'zh');
    });
  }, [projects, workMode]);

  // 展开项目时加载其下会话（默认展开）
  useEffect(() => {
    visibleProjects.forEach((project) => {
      const expanded = expandedProjectIds[project.project_id] ?? true;
      if (expanded) void loadProjectSessions(project.project_id);
    });
  }, [visibleProjects, expandedProjectIds, loadProjectSessions]);

  const nestedSessionIds = useMemo(() => {
    const ids = new Set<string>();
    visibleProjects.forEach((project) => {
      const expanded = expandedProjectIds[project.project_id] ?? true;
      if (!expanded) return;
      (projectSessions[project.project_id] ?? []).forEach((s) => ids.add(s.session_id));
    });
    return ids;
  }, [visibleProjects, expandedProjectIds, projectSessions]);

  const conversations = useMemo(() => {
    // 合并：置顶 + 各项目会话 + 本地新建会话（去重）；已在展开项目下展示的会话不再重复出现在「对话」区
    const merged = new Map<string, Session>();
    pinnedSessions.forEach((s) => merged.set(s.session_id, { ...s, pinned: true }));
    Object.values(projectSessions).flat().forEach((s) => {
      if (!merged.has(s.session_id)) merged.set(s.session_id, s);
    });
    sessions.forEach((s) => {
      if (!merged.has(s.session_id)) merged.set(s.session_id, s);
    });
    let list = [...merged.values()].filter((s) => {
      if (nestedSessionIds.has(s.session_id) && !s.pinned) return false;
      if (s.work_mode) return s.work_mode === workMode;
      return true;
    });
    if (searchText.trim()) {
      const keyword = searchText.trim().toLowerCase();
      list = list.filter((s) => (s.display_title || s.title || '').toLowerCase().includes(keyword));
    }
    return sortSessionsForSidebar(list);
  }, [sessions, pinnedSessions, projectSessions, nestedSessionIds, workMode, searchText]);

  const menuSession = sessionMenuId
    ? sessions.find((s) => s.session_id === sessionMenuId)
      ?? Object.values(projectSessions).flat().find((s) => s.session_id === sessionMenuId)
      ?? pinnedSessions.find((s) => s.session_id === sessionMenuId)
      ?? null
    : null;
  const menuProject = projectMenuId
    ? visibleProjects.find((p) => p.project_id === projectMenuId) ?? null
    : null;

  const handlePin = async (session: Session) => {
    setSessionMenuId(null);
    try {
      await pinSession(session.session_id, !session.pinned);
    } catch { /* 静默 */ }
  };

  const handleToggleProject = (project: ProjectInfo) => {
    const wasExpanded = expandedProjectIds[project.project_id] ?? true;
    toggleProjectExpanded(project.project_id);
    setSelectedProject(project);
    if (!wasExpanded) void loadProjectSessions(project.project_id);
  };

  const handleNewInProject = (project: ProjectInfo) => {
    setSelectedProject(project);
    setProjectMenuId(null);
    onNewChat();
  };

  const handlePinProject = async (project: ProjectInfo) => {
    setProjectMenuId(null);
    if (isDefaultProject(project)) return;
    try {
      await pinProject(project.project_id, !project.pinned);
    } catch { /* 静默 */ }
  };

  const openRenameProject = (project: ProjectInfo) => {
    setProjectMenuId(null);
    if (isDefaultProject(project)) return;
    setRenameProjectError(null);
    setRenameProjectValue(project.name);
    setRenameProjectTarget(project);
  };

  const openDeleteProject = (project: ProjectInfo) => {
    setProjectMenuId(null);
    if (isDefaultProject(project)) return;
    setDeleteProjectError(null);
    setDeleteProjectTarget(project);
  };

  const handleRenameProjectSubmit = async () => {
    if (!renameProjectTarget) return;
    const nextName = renameProjectValue.trim();
    if (!nextName) {
      setRenameProjectError(t('multiSession.project.namePlaceholder'));
      return;
    }
    setRenameProjectBusy(true);
    setRenameProjectError(null);
    try {
      await renameProject(renameProjectTarget.project_id, nextName);
      setRenameProjectTarget(null);
    } catch (error) {
      setRenameProjectError(error instanceof Error ? error.message : String(error));
    } finally {
      setRenameProjectBusy(false);
    }
  };

  const handleDeleteProjectSubmit = async () => {
    if (!deleteProjectTarget || isDefaultProject(deleteProjectTarget)) return;
    setDeleteProjectBusy(true);
    setDeleteProjectError(null);
    try {
      await removeProject(deleteProjectTarget.project_id);
      setDeleteProjectTarget(null);
    } catch (error) {
      setDeleteProjectError(error instanceof Error ? error.message : String(error));
    } finally {
      setDeleteProjectBusy(false);
    }
  };

  const deleteProjectDescription = deleteProjectTarget
    ? t('multiSession.project.deleteProjectDescription', {
      projectName: getProjectDisplayName(deleteProjectTarget),
    }).replace(/<\/?name>/g, '')
    : '';

  if (collapsed) {
    return (
      <div className="sidebar sidebar--collapsed">
        <button className="icon-btn" onClick={onToggleCollapse} title="展开侧边栏">
          <PanelLeftOpen size={18} />
        </button>
        <button className="icon-btn" onClick={onNewChat} title="新建对话">
          <SquarePen size={18} />
        </button>
        <div className="sidebar-collapsed-spacer" />
        <div className="sidebar-avatar sidebar-avatar--sm" title={username}>
          {(username || 'U').slice(0, 1).toUpperCase()}
        </div>
      </div>
    );
  }

  return (
    <div className="sidebar">
      {/* 头部 */}
      <div className="sidebar-header">
        <LogoMark />
        <span className="sidebar-title">华为智能体一体机</span>
        <div className="sidebar-header-actions">
          <button
            className="icon-btn icon-btn--sm"
            title="搜索对话"
            onClick={() => { setSearchOpen((v) => !v); setSearchText(''); }}
          >
            <Search size={16} />
          </button>
          <button className="icon-btn icon-btn--sm" title="收起侧边栏" onClick={onToggleCollapse}>
            <PanelLeftClose size={16} />
          </button>
        </div>
      </div>

      {searchOpen ? (
        <div className="sidebar-search">
          <input
            autoFocus
            className="sidebar-search-input"
            placeholder="搜索对话…"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
        </div>
      ) : null}

      {/* 主导航 */}
      <nav className="sidebar-nav">
        <button className={`sidebar-nav-item ${activeNav === 'chat' ? 'is-active' : ''}`} onClick={onNewChat}>
          <SquarePen size={16} className="sidebar-nav-icon" />
          <span>新建对话</span>
        </button>
        <button className={`sidebar-nav-item ${activeNav === 'cron' ? 'is-active' : ''}`} onClick={onOpenCron}>
          <Clock size={16} className="sidebar-nav-icon" />
          <span>定时任务</span>
        </button>
        <button className="sidebar-nav-item" onClick={onOpenPlugins}>
          <LayoutGrid size={16} className="sidebar-nav-icon" />
          <span>插件</span>
        </button>
        <button
          ref={moreMenuAnchorRef}
          className={`sidebar-nav-item ${moreMenuOpen ? 'is-active' : ''}`}
          onClick={() => setMoreMenuOpen((v) => !v)}
        >
          <MoreHorizontal size={16} className="sidebar-nav-icon" />
          <span>更多</span>
        </button>
      </nav>

      <Popup open={moreMenuOpen} anchorRef={moreMenuAnchorRef} onClose={() => setMoreMenuOpen(false)}>
        <div className="menu-pop">
          <button className="menu-item" onClick={() => { setMoreMenuOpen(false); onOpenTools(); }}>
            <span className="menu-item-icon"><Wrench size={15} /></span>
            <span className="menu-item-label">工具面板</span>
            <span className="menu-item-extra">文件 / 记忆 / 产出</span>
          </button>
          <button className="menu-item" onClick={() => { setMoreMenuOpen(false); onOpenSettings(); }}>
            <span className="menu-item-icon"><Settings size={15} /></span>
            <span className="menu-item-label">设置</span>
            <span className="menu-item-extra">主题 / 语言 / 权限</span>
          </button>
        </div>
      </Popup>

      <div className="sidebar-scroll">
        {/* 项目：可展开查看会话；更多菜单支持置顶 / 重命名 / 删除 */}
        <ProjectSectionHeader onCreateClick={openCreateProject} />
        <div className="sidebar-list">
          {visibleProjects.length === 0 ? (
            <div className="sidebar-empty">暂无项目，点击 + 新建</div>
          ) : visibleProjects.map((project) => {
            const expanded = expandedProjectIds[project.project_id] ?? true;
            const isActive = selectedProject?.project_id === project.project_id;
            const hideActions = isDefaultProject(project);
            const nestedSessions = sortSessionsForSidebar(projectSessions[project.project_id] ?? []);
            const displayName = getProjectDisplayName(project);
            return (
              <div key={project.project_id} className="sidebar-project-group">
                <div
                  className={`sidebar-list-item sidebar-project-item ${isActive ? 'is-active' : ''} ${projectMenuId === project.project_id ? 'is-menu-open' : ''}`}
                  title={project.project_dir || displayName}
                >
                  <button
                    type="button"
                    className="sidebar-project-main"
                    onClick={() => handleToggleProject(project)}
                  >
                    <span className="sidebar-project-chevron" aria-hidden>
                      {expanded ? <ProjectChevronDownIcon size={10} /> : <ChevronRight size={14} />}
                    </span>
                    <ProjectSpaceIcon size={15} className="sidebar-list-icon" />
                    <span className="sidebar-list-text">{displayName}</span>
                    {project.pinned && !hideActions ? (
                      <Pin size={12} className="sidebar-pin-icon" aria-hidden />
                    ) : null}
                  </button>
                  <button
                    type="button"
                    className="icon-btn icon-btn--xs sidebar-project-action"
                    title={t('multiSession.project.startConversation', { projectName: displayName })}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleNewInProject(project);
                    }}
                  >
                    <NewProjectIcon size={14} />
                  </button>
                  {hideActions ? null : (
                    <button
                      ref={projectMenuId === project.project_id ? projectMenuAnchorRef : undefined}
                      type="button"
                      className="icon-btn icon-btn--xs sidebar-project-action sidebar-project-menu-btn"
                      title={t('multiSession.moreActions')}
                      aria-label={t('multiSession.moreActions')}
                      onClick={(e) => {
                        e.stopPropagation();
                        setProjectMenuId(projectMenuId === project.project_id ? null : project.project_id);
                      }}
                    >
                      <Ellipsis size={14} />
                    </button>
                  )}
                </div>

                {expanded ? (
                  <div className="sidebar-project-sessions">
                    {nestedSessions.length === 0 ? (
                      <div className="sidebar-empty sidebar-empty--nested">
                        {t('multiSession.project.noConversations')}
                      </div>
                    ) : nestedSessions.map((session) => {
                      const runtime = chatRuntimes[session.session_id];
                      const indicator = getSessionIndicator(runtime, false, session.is_processing, Boolean(runtime?.error));
                      const isSessionActive = activeSessionId === session.session_id;
                      const title = session.display_title || session.title || '新对话';
                      return (
                        <div
                          key={session.session_id}
                          className={`sidebar-list-item sidebar-conv-item sidebar-conv-item--nested ${isSessionActive ? 'is-active' : ''}`}
                          onClick={() => {
                            setSelectedProject(project);
                            onSelectSession(session.session_id);
                          }}
                        >
                          <span className="sidebar-list-text" title={title}>{title}</span>
                          <span className="sidebar-conv-right">
                            {indicator === 'processing' ? (
                              <Loader2 size={13} className="spin sidebar-conv-spinner" />
                            ) : indicator === 'waiting' ? (
                              <span className="sidebar-conv-waiting" title="等待回答" />
                            ) : indicator === 'error' ? (
                              <span className="sidebar-conv-error" title="出错了" />
                            ) : (
                              <span className="sidebar-conv-time">
                                {formatTime(session.last_user_message_at ?? session.last_message_at ?? session.updated_at)}
                              </span>
                            )}
                          </span>
                          <button
                            ref={sessionMenuId === session.session_id ? sessionMenuAnchorRef : undefined}
                            className="icon-btn icon-btn--xs sidebar-conv-menu-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSessionMenuId(sessionMenuId === session.session_id ? null : session.session_id);
                            }}
                          >
                            <Ellipsis size={14} />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>

        {/* 对话（未在展开项目下展示的会话 / 置顶会话） */}
        <div className="sidebar-section-label">对话</div>
        <div className="sidebar-list">
          {conversations.length === 0 ? (
            <div className="sidebar-empty">暂无对话</div>
          ) : conversations.map((session) => {
            const runtime = chatRuntimes[session.session_id];
            const indicator = getSessionIndicator(runtime, false, session.is_processing, Boolean(runtime?.error));
            const isActive = activeSessionId === session.session_id;
            const title = session.display_title || session.title || '新对话';
            return (
              <div
                key={session.session_id}
                className={`sidebar-list-item sidebar-conv-item ${isActive ? 'is-active' : ''}`}
                onClick={() => onSelectSession(session.session_id)}
              >
                {session.pinned
                  ? <Pin size={13} className="sidebar-list-icon sidebar-pin-icon" />
                  : <MessageSquare size={14} className="sidebar-list-icon" />}
                <span className="sidebar-list-text" title={title}>{title}</span>
                <span className="sidebar-conv-right">
                  {indicator === 'processing' ? (
                    <Loader2 size={13} className="spin sidebar-conv-spinner" />
                  ) : indicator === 'waiting' ? (
                    <span className="sidebar-conv-waiting" title="等待回答" />
                  ) : indicator === 'error' ? (
                    <span className="sidebar-conv-error" title="出错了" />
                  ) : (
                    <span className="sidebar-conv-time">
                      {formatTime(session.last_user_message_at ?? session.last_message_at ?? session.updated_at)}
                    </span>
                  )}
                </span>
                <button
                  ref={sessionMenuId === session.session_id ? sessionMenuAnchorRef : undefined}
                  className="icon-btn icon-btn--xs sidebar-conv-menu-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    setSessionMenuId(sessionMenuId === session.session_id ? null : session.session_id);
                  }}
                >
                  <Ellipsis size={14} />
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* 项目菜单 */}
      <Popup open={Boolean(menuProject)} anchorRef={projectMenuAnchorRef} placement="bottom-end" onClose={() => setProjectMenuId(null)}>
        {menuProject ? (
          <div className="menu-pop">
            <button className="menu-item" onClick={() => void handlePinProject(menuProject)}>
              <span className="menu-item-icon"><Pin size={14} /></span>
              <span className="menu-item-label">
                {menuProject.pinned
                  ? t('multiSession.project.unpinProject')
                  : t('multiSession.project.pinProject')}
              </span>
            </button>
            <button className="menu-item" onClick={() => openRenameProject(menuProject)}>
              <span className="menu-item-icon"><Pencil size={14} /></span>
              <span className="menu-item-label">{t('multiSession.project.rename')}</span>
            </button>
            <div className="menu-sep" />
            <button className="menu-item menu-item-danger" onClick={() => openDeleteProject(menuProject)}>
              <span className="menu-item-icon"><Trash2 size={14} /></span>
              <span className="menu-item-label">{t('multiSession.project.deleteProject')}</span>
            </button>
          </div>
        ) : null}
      </Popup>

      {/* 会话菜单 */}
      <Popup open={Boolean(menuSession)} anchorRef={sessionMenuAnchorRef} placement="bottom-end" onClose={() => setSessionMenuId(null)}>
        {menuSession ? (
          <div className="menu-pop">
            <button className="menu-item" onClick={() => void handlePin(menuSession)}>
              <span className="menu-item-icon"><Pin size={14} /></span>
              <span className="menu-item-label">{menuSession.pinned ? '取消置顶' : '置顶'}</span>
            </button>
            <button
              className="menu-item"
              onClick={() => { setSessionMenuId(null); onRenameSession(menuSession); }}
            >
              <span className="menu-item-icon"><Pencil size={14} /></span>
              <span className="menu-item-label">重命名</span>
            </button>
            <div className="menu-sep" />
            <button
              className="menu-item menu-item-danger"
              onClick={() => { setSessionMenuId(null); onDeleteSession(menuSession); }}
            >
              <span className="menu-item-icon"><Trash2 size={14} /></span>
              <span className="menu-item-label">删除</span>
            </button>
          </div>
        ) : null}
      </Popup>

      {/* 底部用户区 */}
      <div className="sidebar-user">
        <div className="sidebar-avatar">{(username || 'U').slice(0, 1).toUpperCase()}</div>
        <span className="sidebar-user-name" title={username}>{username}</span>
        <button
          ref={userMenuAnchorRef}
          className="icon-btn icon-btn--sm"
          onClick={() => setUserMenuOpen((v) => !v)}
        >
          <Ellipsis size={16} />
        </button>
      </div>
      <Popup open={userMenuOpen} anchorRef={userMenuAnchorRef} placement="top-end" onClose={() => setUserMenuOpen(false)}>
        <div className="menu-pop">
          <button className="menu-item" onClick={() => { setUserMenuOpen(false); onOpenSettings(); }}>
            <span className="menu-item-icon"><Settings size={15} /></span>
            <span className="menu-item-label">设置</span>
          </button>
          <div className="menu-sep" />
          <button className="menu-item menu-item-danger" onClick={() => { setUserMenuOpen(false); onLogout(); }}>
            <span className="menu-item-icon"><LogOut size={15} /></span>
            <span className="menu-item-label">退出登录</span>
          </button>
        </div>
      </Popup>

      <CreateProjectDialog
        open={createProjectOpen}
        error={createProjectError}
        submitting={createProjectSubmitting}
        onCancel={closeCreateProject}
        onSubmit={handleCreateProject}
      />

      {renameProjectTarget ? (
        <div className="modal-mask" onClick={() => !renameProjectBusy && setRenameProjectTarget(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div className="modal-title">{t('multiSession.project.rename')}</div>
            </div>
            <div className="modal-body">
              <input
                autoFocus
                className="form-input"
                value={renameProjectValue}
                onChange={(e) => setRenameProjectValue(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') void handleRenameProjectSubmit(); }}
                placeholder={t('multiSession.project.renamePlaceholder')}
                disabled={renameProjectBusy}
              />
              {renameProjectError ? <div className="sidebar-dialog-error">{renameProjectError}</div> : null}
            </div>
            <div className="modal-foot">
              <button className="btn btn-ghost" disabled={renameProjectBusy} onClick={() => setRenameProjectTarget(null)}>
                {t('multiSession.project.cancel')}
              </button>
              <button
                className="btn btn-primary"
                disabled={renameProjectBusy || !renameProjectValue.trim()}
                onClick={() => void handleRenameProjectSubmit()}
              >
                {t('multiSession.project.confirm')}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {deleteProjectTarget ? (
        <div className="modal-mask" onClick={() => !deleteProjectBusy && setDeleteProjectTarget(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div className="modal-title">{t('multiSession.project.deleteProject')}</div>
            </div>
            <div className="modal-body">
              <p style={{ margin: 0, color: 'var(--t2)' }}>{deleteProjectDescription}</p>
              {deleteProjectError ? <div className="sidebar-dialog-error">{deleteProjectError}</div> : null}
            </div>
            <div className="modal-foot">
              <button className="btn btn-ghost" disabled={deleteProjectBusy} onClick={() => setDeleteProjectTarget(null)}>
                {t('multiSession.project.cancel')}
              </button>
              <button
                className="btn btn-dark"
                disabled={deleteProjectBusy}
                onClick={() => void handleDeleteProjectSubmit()}
              >
                {deleteProjectBusy ? '删除中…' : t('multiSession.delete')}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
