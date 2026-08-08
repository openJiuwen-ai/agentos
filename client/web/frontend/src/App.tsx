/**
 * App 主组件 —— 华为智能体一体机 客户端
 *
 * 编排：登录门 → WebSocket 连接（useWebSocket 自动连接）→
 * 首页(/chat/new) / 对话(/chat/:id) / 定时任务 视图切换
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { AgentMode, MediaItem, Permission, Session, UserAnswer } from './types';
import { useWebSocket, mergePersistedGoalCompletionMessages, stampGoalObjectiveMessages } from './hooks';
import { webClient } from './services/webClient';
import { ensureSessionRuntimes, useChatStore, useCronStore, useGoalStore, useSessionStore, useWorkspaceStore } from './stores';
import { useChatRoute } from './multi-session/routing/useChatRoute';
import {
  NEW_CONVERSATION_ID,
  createConversationTitle,
  forgetCreatedConversation,
  registerCreatedConversation,
  resetNewConversationRuntime,
} from './multi-session/state/newConversationLifecycle';
import { createConversationSession } from './multi-session/state/createConversationSession';
import { beginHistoryRestore, HISTORY_GET_METHOD, type HistoryRestoreHandle } from './features/historyRestore';
import { normalizeToolCallPayload, normalizeToolResultPayload } from './features/tool-events/toolEventNormalizer';
import { generateUuidV4 } from './utils/uuid';
import { LoginPage, getLoginUser, clearLoginUser } from './components/auth/LoginPage';
import { Sidebar } from './components/sidebar/Sidebar';
import { ChatHome } from './components/home/ChatHome';
import { ChatView } from './components/chat/ChatView';
import { CronPanel } from './components/sidebar/CronPanel';
import { ToolsDrawer } from './components/sidebar/ToolsDrawer';
import { SettingsDialog, PluginsDialog } from './components/settings/SettingsDialog';
import './App.css';

function generateSessionId(): string {
  const ts = Date.now().toString(16);
  const rand = generateUuidV4().replace(/-/g, '').slice(0, 12);
  return `sess_${ts}_${rand}`;
}

interface Toast {
  id: number;
  message: string;
  isError: boolean;
}

/** 通过聊天创建定时任务:预填到对话输入框的引导文案(用户补全后发送,agent 用 cron_create_job 工具建任务)。 */
const CREATE_CRON_VIA_CHAT_PROMPT = '帮我创建一个定时任务：';

function App() {
  /* ---------- 登录 ---------- */
  const [username, setUsername] = useState<string | null>(() => getLoginUser());

  /* ---------- 路由与会话 ---------- */
  const { route, navigate } = useChatRoute();
  const routeSessionId = route.kind === 'chat-session' ? route.sessionId : null;
  const [sessionId, setSessionId] = useState<string>(NEW_CONVERSATION_ID);
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  /* ---------- UI 状态 ---------- */
  const [activeNav, setActiveNav] = useState<'chat' | 'cron'>('chat');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [pluginsOpen, setPluginsOpen] = useState(false);
  const [permission, setPermission] = useState<Permission>('default');
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<Session | null>(null);
  const [renameTarget, setRenameTarget] = useState<Session | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [cronDraft, setCronDraft] = useState<string | undefined>(undefined);
  const [missingSession, setMissingSession] = useState(false);
  const [dialogBusy, setDialogBusy] = useState(false);

  const initialDataLoadedRef = useRef(false);
  const creatingSessionRef = useRef(false);
  const historyHandlesRef = useRef(new Map<string, HistoryRestoreHandle>());
  const restoredSessionsRef = useRef(new Set<string>());
  const promotedSessionIdsRef = useRef(new Set<string>());
  const toastSeqRef = useRef(0);

  /* ---------- WebSocket ---------- */
  const { isConnected, connectionState, request, sendMessage, cancel, switchMode, sendUserAnswer, refreshGoal, resumeGoal, setGoalObjective } = useWebSocket({
    activeSessionId: sessionId,
    onError: error => pushToast(error, true),
  });

  /* ---------- Toast ---------- */
  const pushToast = useCallback((message: string, isError = false) => {
    const id = ++toastSeqRef.current;
    setToasts(prev => [...prev.slice(-3), { id, message, isError }]);
    window.setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 3200);
  }, []);

  /* ---------- 路由 → sessionId ---------- */
  useEffect(() => {
    setSessionId(routeSessionId ?? NEW_CONVERSATION_ID);
  }, [routeSessionId]);

  useEffect(() => {
    ensureSessionRuntimes(sessionId);
    useChatStore.getState().setActiveSessionId(sessionId);
  }, [sessionId]);

  /* ---------- 首次连接：拉配置 / 项目 / 定时任务 ---------- */
  useEffect(() => {
    if (!isConnected || initialDataLoadedRef.current) return;
    initialDataLoadedRef.current = true;
    void (async () => {
      try {
        const config = await request<Record<string, string>>('config.get');
        setPermission(config?.permissions_enabled === 'false' ? 'full_access' : 'default');
      } catch {
        /* 配置拉取失败时保持默认权限 */
      }
      // 同步获取多模型列表
      void (async () => {
        try {
          const resp = await request<{ models: import('./types').ModelEntry[]; active_model: string }>('models.list');
          if (resp?.models) {
            useSessionStore.getState().setAvailableModels(resp.models, resp.active_model);
          }
        } catch (error) {
          console.warn('获取模型列表失败:', error);
        }
      })();
      void (async () => {
        await useWorkspaceStore.getState().loadProjects();
        const { projects } = useWorkspaceStore.getState();
        await Promise.all(projects.map(p => useWorkspaceStore.getState().loadProjectSessions(p.project_id)));
      })();
      void useCronStore.getState().loadJobs();
    })();
  }, [isConnected, request]);

  /* ---------- 历史恢复 ---------- */
  const restoreHistory = useCallback(
    (sid: string) => {
      const chatStore = useChatStore.getState();
      chatStore.setLoadingHistory(sid, true);
      const handle = beginHistoryRestore({
        sessionId: sid,
        onReady: messages => {
          useChatStore.getState().replaceHistoryMessages(sid, stampGoalObjectiveMessages(sid, mergePersistedGoalCompletionMessages(sid, messages)));
          useChatStore.getState().setLoadingHistory(sid, false);
          historyHandlesRef.current.delete(sid);
        },
        onEmpty: () => {
          useChatStore.getState().replaceHistoryMessages(sid, []);
          useChatStore.getState().setLoadingHistory(sid, false);
          historyHandlesRef.current.delete(sid);
        },
        onToolReplay: items => {
          items.forEach(item => {
            if (item.kind === 'tool_call') {
              const n = normalizeToolCallPayload(item.payload);
              useChatStore.getState().addToolCall(
                sid,
                {
                  id: n.id,
                  name: n.name,
                  arguments: n.arguments,
                  description: n.description,
                  formatted_args: n.formatted_args,
                  display_name: n.display_name,
                  memberName: n.memberName,
                },
                { startedAt: item.at }
              );
            } else {
              const n = normalizeToolResultPayload(item.payload);
              useChatStore.getState().addToolResult(
                sid,
                {
                  toolName: n.toolName,
                  result: n.result,
                  success: n.success,
                  toolCallId: n.toolCallId,
                  summary: n.summary,
                },
                { updatedAt: item.at }
              );
            }
          });
          useChatStore.getState().settleHistoricalToolExecutions(sid);
        },
        onReasoningReplay: items => {
          useChatStore.getState().restoreReasoningSegments(sid, items);
        },
      });
      historyHandlesRef.current.set(sid, handle);
      void request(HISTORY_GET_METHOD, { session_id: sid, page_idx: 1 }).catch(error => {
        handle.dispose();
        historyHandlesRef.current.delete(sid);
        useChatStore.getState().setLoadingHistory(sid, false);
        console.warn('[history] 加载失败:', error);
      });
    },
    [request]
  );

  /* ---------- 路由会话：元数据 + 历史 ---------- */
  useEffect(() => {
    if (!isConnected || !routeSessionId) {
      setMissingSession(false);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const session = await request<Session>('session.get_metadata', { session_id: routeSessionId });
        if (cancelled) return;
        useSessionStore.getState().updateSession(routeSessionId, session);
        useSessionStore.getState().setCurrentSession(session);
        if (session.model) {
          useSessionStore.getState().setSelectedModelName(routeSessionId, session.model);
        }
        setMissingSession(false);
      } catch {
        if (!cancelled) setMissingSession(true);
        return;
      }
      // 刚创建提升的会话无需拉历史（消息都在本地）
      if (promotedSessionIdsRef.current.has(routeSessionId)) return;
      if (restoredSessionsRef.current.has(routeSessionId)) return;
      restoredSessionsRef.current.add(routeSessionId);
      restoreHistory(routeSessionId);
    })();
    return () => {
      cancelled = true;
    };
  }, [isConnected, routeSessionId, request, restoreHistory]);

  /* ---------- Goal 状态刷新（切会话/刷新后补一次 get + active 时 resume 抢听筒） ---------- */
  useEffect(() => {
    if (!isConnected || !sessionId || sessionId === NEW_CONVERSATION_ID) return;
    void (async () => {
      await refreshGoal(sessionId);
      if (sessionIdRef.current !== sessionId) return;
      const goal = useGoalStore.getState().runtimes[sessionId]?.goal;
      if (goal?.status === 'active') {
        void resumeGoal(sessionId);
      }
    })();
  }, [isConnected, sessionId, refreshGoal, resumeGoal]);

  /* ---------- 权限 ---------- */
  const handleChangePermission = useCallback(
    (next: Permission) => {
      setPermission(next);
      void request('config.set', {
        config: { permissions_enabled: next === 'default' ? 'true' : 'false' },
      })
        .then(() => {
          pushToast(next === 'default' ? '已切换为默认权限' : '已开启完全访问权限');
        })
        .catch(error => {
          pushToast(error instanceof Error ? error.message : '权限设置失败', true);
        });
    },
    [request, pushToast]
  );

  /* ---------- 新建对话 ---------- */
  const enterNewConversation = useCallback(() => {
    const runtime = useSessionStore.getState().getRuntime(sessionIdRef.current);
    const selectedModelName = useSessionStore.getState().defaultModelName ?? runtime?.selectedModelName ?? null;
    resetNewConversationRuntime({
      mode: runtime?.mode ?? 'agent',
      selectedModelName,
      projectDir: useWorkspaceStore.getState().selectedProject?.project_dir ?? null,
    });
    setSessionId(NEW_CONVERSATION_ID);
    useSessionStore.getState().setCurrentSession(null);
    setActiveNav('chat');
    setMissingSession(false);
    navigate({ kind: 'chat-new' });
  }, [navigate]);

  /* ---------- 选择会话 ---------- */
  const handleSelectSession = useCallback(
    (targetSessionId: string) => {
      if (targetSessionId === sessionIdRef.current) return;
      setActiveNav('chat');
      navigate({ kind: 'chat-session', sessionId: targetSessionId });
    },
    [navigate]
  );

  /* ---------- 发送消息（含新会话创建流） ---------- */
  const handleSendMessage = useCallback(
    async (content: string, mediaItems?: MediaItem[]) => {
      const currentSessionId = sessionIdRef.current;
      if (!currentSessionId) return;

      if (currentSessionId !== NEW_CONVERSATION_ID) {
        const sent = await sendMessage(content, currentSessionId, mediaItems);
        if (!sent) {
          useChatStore.getState().setInputValue(currentSessionId, content);
        }
        return;
      }

      // 首页首条消息：先创建会话再发送
      if (creatingSessionRef.current) return;
      creatingSessionRef.current = true;
      useChatStore.getState().setProcessing(NEW_CONVERSATION_ID, true);
      const newSid = generateSessionId();
      const newRuntime = useSessionStore.getState().getRuntime(NEW_CONVERSATION_ID);
      const runtimeSettings = {
        mode: newRuntime?.mode ?? ('agent' as AgentMode),
        selectedModelName: useSessionStore.getState().getEffectiveModelName(NEW_CONVERSATION_ID),
        projectDir: newRuntime?.projectDirectory ?? null,
      };
      const selectedProject = useWorkspaceStore.getState().selectedProject;
      const workMode = useWorkspaceStore.getState().workMode;

      try {
        const createParams: Record<string, unknown> = {
          session_id: newSid,
          mode: runtimeSettings.mode,
          title: createConversationTitle(content).slice(0, 100),
          work_mode: workMode,
        };
        if (runtimeSettings.selectedModelName) createParams.model = runtimeSettings.selectedModelName;
        if (selectedProject?.project_id) createParams.project_id = selectedProject.project_id;
        if (selectedProject?.project_dir) createParams.project_dir = selectedProject.project_dir;

        const created = await createConversationSession(request, createParams, newSid);
        const createdSession = registerCreatedConversation(created.session_id, runtimeSettings, Date.now(), content, {
          project_id: created.project_id || selectedProject?.project_id || '',
          project_dir: created.project_dir || selectedProject?.project_dir || '',
          work_mode: created.work_mode || workMode,
        });
        // 迁移首页已选技能
        const pendingSkills = useSessionStore.getState().getRuntime(NEW_CONVERSATION_ID)?.selectedSkills ?? [];
        pendingSkills.forEach(skill => useSessionStore.getState().addSelectedSkill(newSid, skill));
        useSessionStore.getState().clearSelectedSkills(NEW_CONVERSATION_ID);
        useWorkspaceStore.getState().upsertSession(createdSession, { isNew: true });
        promotedSessionIdsRef.current.add(newSid);
        useChatStore.getState().setProcessing(NEW_CONVERSATION_ID, false);
        setSessionId(newSid);
        navigate({ kind: 'chat-session', sessionId: newSid }, { replace: true });

        const goalArmed = useGoalStore.getState().runtimes[NEW_CONVERSATION_ID]?.armed ?? false;
        useGoalStore.getState().setArmed(NEW_CONVERSATION_ID, false);
        if (goalArmed) {
          useChatStore.getState().addMessage(newSid, {
            id: `user-${Date.now()}`,
            role: 'user',
            content,
            timestamp: new Date().toISOString(),
            isGoalObjectiveMessage: true,
          });
          await setGoalObjective(newSid, content);
        } else {
          const sent = await sendMessage(content, newSid, mediaItems);
          if (!sent) {
            useChatStore.getState().setInputValue(newSid, content);
          }
        }
      } catch (error) {
        useChatStore.getState().setProcessing(NEW_CONVERSATION_ID, false);
        useChatStore.getState().setThinking(NEW_CONVERSATION_ID, false);
        useChatStore.getState().setInputValue(NEW_CONVERSATION_ID, content);
        pushToast(error instanceof Error ? `创建会话失败：${error.message}` : '创建会话失败', true);
      } finally {
        creatingSessionRef.current = false;
      }
    },
    [navigate, pushToast, request, sendMessage, setGoalObjective]
  );

  /* ---------- 停止 ---------- */
  const handleCancel = useCallback(() => {
    const currentSessionId = sessionIdRef.current;
    if (!currentSessionId || currentSessionId === NEW_CONVERSATION_ID) return;
    void cancel(currentSessionId);
  }, [cancel]);

  /* ---------- 反问回答 ---------- */
  const handleSubmitAnswer = useCallback(
    (requestId: string, answers: UserAnswer[]) => {
      const currentSessionId = sessionIdRef.current;
      if (!currentSessionId || currentSessionId === NEW_CONVERSATION_ID) return;
      void sendUserAnswer(currentSessionId, requestId, answers);
      useChatStore.getState().setPendingQuestion(currentSessionId, null);
    },
    [sendUserAnswer]
  );

  const handleDismissQuestion = useCallback(() => {
    const currentSessionId = sessionIdRef.current;
    if (!currentSessionId) return;
    useChatStore.getState().setPendingQuestion(currentSessionId, null);
  }, []);

  const handleSkipQuestion = useCallback(() => {
    const currentSessionId = sessionIdRef.current;
    if (!currentSessionId) return;
    const pending = useChatStore.getState().getRuntime(currentSessionId)?.pendingQuestion;
    if (pending) {
      const answers: UserAnswer[] = (pending.questions ?? []).map(q => ({
        question: q.question,
        selected_options: [],
      }));
      void sendUserAnswer(currentSessionId, pending.request_id, answers);
    }
    useChatStore.getState().setPendingQuestion(currentSessionId, null);
  }, [sendUserAnswer]);

  /* ---------- 模式切换 ---------- */
  const handleSwitchMode = useCallback(
    (mode: AgentMode) => {
      const currentSessionId = sessionIdRef.current;
      if (!currentSessionId) return;
      if (currentSessionId === NEW_CONVERSATION_ID) {
        useSessionStore.getState().setMode(NEW_CONVERSATION_ID, mode);
        return;
      }
      void switchMode(currentSessionId, mode).catch(error => {
        pushToast(error instanceof Error ? error.message : '切换模式失败', true);
      });
    },
    [switchMode, pushToast]
  );

  /* ---------- 定时任务草稿 ---------- */
  const handleSchedule = useCallback((draftText: string) => {
    setCronDraft(draftText.trim());
    setActiveNav('cron');
  }, []);

  /* ---------- 通过聊天创建定时任务(切到新对话 + 预填引导文案;agent 用 cron_create_job 工具建任务) ---------- */
  const handleCreateCronViaChat = useCallback(() => {
    enterNewConversation(); // 切到新会话(内部已 setActiveNav('chat') + navigate chat-new)
    // setInputValue 对不存在的 runtime 是 no-op,先 ensureRuntime 再写,确保预填生效
    useChatStore.getState().ensureRuntime(NEW_CONVERSATION_ID);
    useChatStore.getState().setInputValue(NEW_CONVERSATION_ID, CREATE_CRON_VIA_CHAT_PROMPT);
  }, [enterNewConversation]);

  /* ---------- 删除会话 ---------- */
  const handleDeleteSession = useCallback(async () => {
    if (!deleteTarget) return;
    setDialogBusy(true);
    try {
      await request('session.delete', { session_id: deleteTarget.session_id });
      forgetCreatedConversation(deleteTarget.session_id);
      restoredSessionsRef.current.delete(deleteTarget.session_id);
      useSessionStore.getState().removeSession(deleteTarget.session_id);
      useSessionStore.getState().removeRuntime(deleteTarget.session_id);
      useChatStore.getState().removeRuntime(deleteTarget.session_id);
      useGoalStore.getState().removeRuntime(deleteTarget.session_id);
      void useWorkspaceStore.getState().refreshSessionWorkspace(deleteTarget);
      pushToast('会话已删除');
      if (sessionIdRef.current === deleteTarget.session_id) {
        enterNewConversation();
      }
    } catch (error) {
      pushToast(error instanceof Error ? error.message : '删除失败', true);
    } finally {
      setDialogBusy(false);
      setDeleteTarget(null);
    }
  }, [deleteTarget, enterNewConversation, pushToast, request]);

  /* ---------- 重命名会话 ---------- */
  const handleRenameSession = useCallback(async () => {
    if (!renameTarget || !renameValue.trim()) return;
    setDialogBusy(true);
    try {
      await useWorkspaceStore.getState().renameSession(renameTarget.session_id, renameValue.trim());
      setRenameTarget(null);
      setRenameValue('');
    } catch (error) {
      pushToast(error instanceof Error ? error.message : '重命名失败', true);
    } finally {
      setDialogBusy(false);
    }
  }, [pushToast, renameTarget, renameValue]);

  /* ---------- 退出登录 ---------- */
  const handleLogout = useCallback(() => {
    clearLoginUser();
    webClient.disconnect();
    window.location.hash = '';
    window.location.reload();
  }, []);

  /* ---------- 派生状态 ---------- */
  const sessions = useSessionStore(s => s.sessions);
  const currentSession = useSessionStore(s => s.currentSession);
  const sessionRuntime = useSessionStore(s => s.runtimes[sessionId]);
  const chatRuntime = useChatStore(s => s.runtimes[sessionId]);
  const isNewSession = sessionId === NEW_CONVERSATION_ID;
  const isProcessing = chatRuntime?.isProcessing ?? false;

  const sessionTitle = useMemo(() => {
    if (isNewSession) return '';
    const session = currentSession?.session_id === sessionId ? currentSession : sessions.find(s => s.session_id === sessionId);
    return (session?.display_title || session?.title || '').trim();
  }, [currentSession, isNewSession, sessionId, sessions]);

  /* ---------- 登录门 ---------- */
  if (!username) {
    return <LoginPage onLogin={setUsername} />;
  }

  const connecting = connectionState !== 'ready';

  return (
    <div className="app-shell">
      <Sidebar
        username={username}
        activeSessionId={isNewSession ? null : sessionId}
        activeNav={activeNav}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(v => !v)}
        onNewChat={enterNewConversation}
        onOpenCron={() => setActiveNav('cron')}
        onOpenPlugins={() => setPluginsOpen(true)}
        onOpenTools={() => setToolsOpen(true)}
        onOpenSettings={() => setSettingsOpen(true)}
        onLogout={handleLogout}
        onSelectSession={handleSelectSession}
        onRenameSession={session => {
          setRenameTarget(session);
          setRenameValue(session.display_title || session.title || '');
        }}
        onDeleteSession={setDeleteTarget}
      />

      <main className="app-main">
        {activeNav === 'cron' ? (
          <CronPanel
            onToast={pushToast}
            initialDraft={cronDraft}
            onConsumeDraft={() => setCronDraft(undefined)}
            onOpenSession={handleSelectSession}
            onCreateViaChat={handleCreateCronViaChat}
          />
        ) : isNewSession ? (
          <ChatHome
            isProcessing={isProcessing}
            disabled={!isConnected}
            permission={permission}
            onChangePermission={handleChangePermission}
            onSend={handleSendMessage}
            onCancel={handleCancel}
            onSchedule={handleSchedule}
            mode={sessionRuntime?.mode ?? 'agent'}
            onSwitchMode={handleSwitchMode}
          />
        ) : missingSession ? (
          <div className="app-missing">
            <div className="app-missing-text">会话不存在或已被删除</div>
            <button className="btn btn-primary" onClick={enterNewConversation}>
              返回首页
            </button>
          </div>
        ) : (
          <ChatView
            sessionId={sessionId}
            title={sessionTitle}
            isProcessing={isProcessing}
            permission={permission}
            onChangePermission={handleChangePermission}
            mode={sessionRuntime?.mode ?? 'agent'}
            onSwitchMode={handleSwitchMode}
            onSend={handleSendMessage}
            onCancel={handleCancel}
            onSchedule={handleSchedule}
            onSubmitAnswer={handleSubmitAnswer}
            onSkipQuestion={handleSkipQuestion}
            onDismissQuestion={handleDismissQuestion}
            modelBadge={useSessionStore.getState().getEffectiveModelName(sessionId) ?? undefined}
          />
        )}

        {/* 连接中遮罩 */}
        {connecting ? (
          <div className="app-connecting">
            <div className="app-connecting-card">
              <div className="app-connecting-spinner" />
              <div className="app-connecting-text">{connectionState === 'reconnecting' ? '连接已断开，正在重连…' : '正在连接后端服务…'}</div>
              <div className="app-connecting-sub">请确认 jiuwenswarm 后端已启动（ws://localhost:19000）</div>
              <button className="btn btn-ghost btn-sm" onClick={() => webClient.connect()}>
                重新连接
              </button>
            </div>
          </div>
        ) : null}
      </main>

      {/* 抽屉与弹窗 */}
      {toolsOpen ? <ToolsDrawer sessionId={isNewSession ? null : sessionId} onClose={() => setToolsOpen(false)} /> : null}
      {settingsOpen ? <SettingsDialog permission={permission} onChangePermission={handleChangePermission} onClose={() => setSettingsOpen(false)} /> : null}
      {pluginsOpen ? <PluginsDialog onClose={() => setPluginsOpen(false)} /> : null}

      {/* 删除确认 */}
      {deleteTarget ? (
        <div className="modal-mask" onClick={() => setDeleteTarget(null)}>
          <div className="modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <div className="modal-title">删除对话</div>
            </div>
            <div className="modal-body">
              <p style={{ margin: 0, color: 'var(--t2)' }}>确定删除「{deleteTarget.display_title || deleteTarget.title || '新对话'}」吗？此操作不可恢复。</p>
            </div>
            <div className="modal-foot">
              <button className="btn btn-ghost" onClick={() => setDeleteTarget(null)}>
                取消
              </button>
              <button className="btn btn-dark" disabled={dialogBusy} onClick={() => void handleDeleteSession()}>
                {dialogBusy ? '删除中…' : '删除'}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* 重命名 */}
      {renameTarget ? (
        <div className="modal-mask" onClick={() => setRenameTarget(null)}>
          <div className="modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-head">
              <div className="modal-title">重命名对话</div>
            </div>
            <div className="modal-body">
              <input
                autoFocus
                className="form-input"
                value={renameValue}
                onChange={e => setRenameValue(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') void handleRenameSession();
                }}
                placeholder="请输入新的对话名称"
              />
            </div>
            <div className="modal-foot">
              <button className="btn btn-ghost" onClick={() => setRenameTarget(null)}>
                取消
              </button>
              <button className="btn btn-primary" disabled={dialogBusy || !renameValue.trim()} onClick={() => void handleRenameSession()}>
                确定
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* Toast */}
      <div className="toast-wrap">
        {toasts.map(toast => (
          <div key={toast.id} className={`toast ${toast.isError ? 'toast-error' : ''}`}>
            {toast.message}
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;
