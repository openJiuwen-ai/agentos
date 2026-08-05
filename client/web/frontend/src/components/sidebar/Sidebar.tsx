/**
 * 侧边栏 —— 按 UI_design/对话-首页 设计稿实现
 * 结构：Logo 头部 / 新建对话·定时任务·插件·更多 / 项目列表 / 对话列表 / 底部用户区
 */
import { useMemo, useRef, useState } from 'react';
import {
  SquarePen, Clock, LayoutGrid, MoreHorizontal, Search, PanelLeftClose, PanelLeftOpen,
  Folder, Pin, Pencil, Trash2, Ellipsis, Settings, LogOut, Wrench, Loader2, MessageSquare,
} from 'lucide-react';
import type { Session } from '../../types';
import { useChatStore, useSessionStore, useWorkspaceStore } from '../../stores';
import { getProjectDisplayName } from '../../stores/workspaceStore';
import { sortSessionsForSidebar, getSessionIndicator } from '../../multi-session/sidebar/sidebarModel';
import { Popup } from '../common/Popup';
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
  const sessions = useSessionStore((s) => s.sessions);
  const projects = useWorkspaceStore((s) => s.projects);
  const projectSessions = useWorkspaceStore((s) => s.projectSessions);
  const pinnedSessions = useWorkspaceStore((s) => s.pinnedSessions);
  const loadProjectSessions = useWorkspaceStore((s) => s.loadProjectSessions);
  const selectedProject = useWorkspaceStore((s) => s.selectedProject);
  const setSelectedProject = useWorkspaceStore((s) => s.setSelectedProject);
  const workMode = useWorkspaceStore((s) => s.workMode);
  const pinSession = useWorkspaceStore((s) => s.pinSession);
  const chatRuntimes = useChatStore((s) => s.runtimes);

  const [sessionMenuId, setSessionMenuId] = useState<string | null>(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchText, setSearchText] = useState('');
  const sessionMenuAnchorRef = useRef<HTMLButtonElement | null>(null);
  const userMenuAnchorRef = useRef<HTMLButtonElement | null>(null);
  const moreMenuAnchorRef = useRef<HTMLButtonElement | null>(null);

  const visibleProjects = useMemo(
    () => projects.filter((p) => !p.hidden && (p.work_mode ?? workMode) === workMode),
    [projects, workMode],
  );

  const conversations = useMemo(() => {
    // 合并：置顶 + 各项目会话 + 本地新建会话（去重）
    const merged = new Map<string, Session>();
    pinnedSessions.forEach((s) => merged.set(s.session_id, { ...s, pinned: true }));
    if (selectedProject) {
      (projectSessions[selectedProject.project_id] ?? []).forEach((s) => {
        if (!merged.has(s.session_id)) merged.set(s.session_id, s);
      });
    } else {
      Object.values(projectSessions).flat().forEach((s) => {
        if (!merged.has(s.session_id)) merged.set(s.session_id, s);
      });
    }
    sessions.forEach((s) => {
      if (!merged.has(s.session_id)) merged.set(s.session_id, s);
    });
    let list = [...merged.values()].filter((s) => {
      if (s.work_mode) return s.work_mode === workMode;
      return true;
    });
    if (searchText.trim()) {
      const keyword = searchText.trim().toLowerCase();
      list = list.filter((s) => (s.display_title || s.title || '').toLowerCase().includes(keyword));
    }
    return sortSessionsForSidebar(list);
  }, [sessions, pinnedSessions, projectSessions, selectedProject, workMode, searchText]);

  const menuSession = sessionMenuId ? sessions.find((s) => s.session_id === sessionMenuId) ?? null : null;

  const handlePin = async (session: Session) => {
    setSessionMenuId(null);
    try {
      await pinSession(session.session_id, !session.pinned);
    } catch { /* 静默 */ }
  };

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
        {/* 项目 */}
        <div className="sidebar-section-label">项目</div>
        <div className="sidebar-list">
          {visibleProjects.length === 0 ? (
            <div className="sidebar-empty">暂无项目</div>
          ) : visibleProjects.map((project) => {
            const isActive = selectedProject?.project_id === project.project_id;
            return (
              <button
                key={project.project_id}
                className={`sidebar-list-item ${isActive ? 'is-active' : ''}`}
                title={project.project_dir || getProjectDisplayName(project)}
                onClick={() => {
                  const next = isActive ? null : project;
                  setSelectedProject(next);
                  if (next) void loadProjectSessions(next.project_id);
                }}
              >
                <Folder size={15} className="sidebar-list-icon" />
                <span className="sidebar-list-text">{getProjectDisplayName(project)}</span>
              </button>
            );
          })}
        </div>

        {/* 对话 */}
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
    </div>
  );
}
