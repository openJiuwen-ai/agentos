/**
 * 消息列表 —— 按 UI_design/工作-PPT生成中 设计稿实现
 * 用户气泡（右侧灰底+技能chip）/ 助手头像+Markdown / 工具状态行 / 思考过程折叠块 / 媒体与文件卡片
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Search, Box, TerminalSquare, PencilLine, Wrench, Loader2, ChevronDown, ChevronRight,
  Download, FileText, Brain, AlertCircle,
} from 'lucide-react';
import type { FileDownloadItem, MediaItem, Message, ToolExecution, UserAnswer } from '../types';
import { useChatStore, type ReasoningSegment } from '../stores/chatStore';
import { MarkdownRenderer } from './MarkdownRenderer';
import { AskUserQuestionCard } from './AskUserQuestionCard';
import mascot from '../assets/design/mascot.png';
import './ChatView.css';

/* ---------- 工具状态行 ---------- */

type ToolCategory = 'explore' | 'skill' | 'run' | 'edit' | 'other';

function toolCategoryOf(name: string): ToolCategory {
  const n = name.toLowerCase();
  if (/skill/.test(n)) return 'skill';
  if (/read|grep|glob|list|search|ls|find|explore|scan|web/.test(n)) return 'explore';
  if (/bash|shell|run|cmd|exec|terminal|command/.test(n)) return 'run';
  if (/write|edit|patch|create|modify|save/.test(n)) return 'edit';
  return 'other';
}

const TOOL_ICONS: Record<ToolCategory, typeof Search> = {
  explore: Search,
  skill: Box,
  run: TerminalSquare,
  edit: PencilLine,
  other: Wrench,
};

function toolStatusText(exec: ToolExecution): string {
  const call = exec.toolCall;
  if (call.display_name) return call.display_name;
  if (call.description) return call.description;
  const category = toolCategoryOf(call.name);
  if (category === 'run') {
    const cmd = typeof call.arguments?.command === 'string'
      ? call.arguments.command
      : typeof call.arguments?.cmd === 'string'
        ? call.arguments.cmd
        : '';
    return cmd ? `已运行 ${cmd.length > 48 ? `${cmd.slice(0, 48)}…` : cmd}` : '已运行命令';
  }
  if (category === 'explore') return '已探索';
  if (category === 'skill') return '已调取技能';
  if (category === 'edit') return '已编辑文件';
  return call.name;
}

function ToolStatusLine({ exec }: { exec: ToolExecution }) {
  const [expanded, setExpanded] = useState(false);
  const category = toolCategoryOf(exec.toolCall.name);
  const Icon = TOOL_ICONS[category];
  const pending = exec.status === 'pending';
  const failed = exec.status === 'error' || exec.status === 'timeout';
  const hasDetail = Boolean(exec.result?.result || exec.toolCall.formatted_args);

  return (
    <div className={`tool-line ${failed ? 'is-failed' : ''}`}>
      <button className="tool-line-main" onClick={() => hasDetail && setExpanded((v) => !v)}>
        {pending ? <Loader2 size={13} className="spin tool-line-icon is-pending" /> : <Icon size={13} className="tool-line-icon" />}
        <span className="tool-line-text">{toolStatusText(exec)}</span>
        {hasDetail ? (expanded ? <ChevronDown size={12} className="tool-line-caret" /> : <ChevronRight size={12} className="tool-line-caret" />) : null}
        {failed ? <span className="tool-line-badge">{exec.status === 'timeout' ? '超时' : '失败'}</span> : null}
      </button>
      {expanded && hasDetail ? (
        <pre className="tool-line-detail">
          {(exec.result?.result || exec.toolCall.formatted_args || '').slice(0, 4000)}
        </pre>
      ) : null}
    </div>
  );
}

/* ---------- 思考过程 ---------- */

function ReasoningBlock({ segments }: { segments: ReasoningSegment[] }) {
  const [expanded, setExpanded] = useState(false);
  const allClosed = segments.every((s) => s.closed);
  const text = segments.map((s) => s.text).join('\n');

  if (!text.trim()) return null;
  return (
    <div className="reasoning-block">
      <button className="reasoning-head" onClick={() => setExpanded((v) => !v)}>
        <Brain size={13} />
        <span>{allClosed ? '思考过程' : '正在思考…'}</span>
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
      </button>
      {expanded ? <div className="reasoning-text">{text}</div> : null}
    </div>
  );
}

/* ---------- 媒体与文件 ---------- */

function mediaSrc(item: MediaItem): string | null {
  if (item.url) return item.url;
  const base64 = item.base64Data ?? item.base64_data;
  if (base64) return `data:${item.mimeType ?? item.mime_type};base64,${base64}`;
  return null;
}

function MediaGallery({ items }: { items: MediaItem[] }) {
  return (
    <div className="msg-media">
      {items.map((item, index) => {
        const src = mediaSrc(item);
        if (item.type === 'image' && src) {
          return <img key={index} src={src} alt={item.filename} className="msg-media-img" />;
        }
        return (
          <span key={index} className="msg-media-file">
            <FileText size={13} />
            <span>{item.filename}</span>
          </span>
        );
      })}
    </div>
  );
}

function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function FileCards({ items }: { items: FileDownloadItem[] }) {
  return (
    <div className="msg-files">
      {items.map((file, index) => (
        <a
          key={`${file.name}-${index}`}
          className="msg-file-card"
          href={file.download_url}
          download={file.name}
          target="_blank"
          rel="noreferrer"
        >
          <FileText size={16} className="msg-file-icon" />
          <span className="msg-file-info">
            <span className="msg-file-name">{file.name}</span>
            {file.size ? <span className="msg-file-size">{formatFileSize(file.size)}</span> : null}
          </span>
          <Download size={14} className="msg-file-download" />
        </a>
      ))}
    </div>
  );
}

/* ---------- 消息行 ---------- */

function UserMessageRow({ message }: { message: Message }) {
  return (
    <div className="msg-row msg-row--user">
      <div className="msg-user-bubble">
        {message.skills && message.skills.length > 0 ? (
          <div className="msg-user-skills">
            {message.skills.map((skill) => (
              <span key={skill} className="skill-chip">
                <Box size={12} />
                <span>{skill}</span>
              </span>
            ))}
          </div>
        ) : null}
        {message.mediaItems && message.mediaItems.length > 0 ? <MediaGallery items={message.mediaItems} /> : null}
        {message.content ? <div className="msg-user-text">{message.content}</div> : null}
      </div>
    </div>
  );
}

function AssistantMessageRow({ message }: { message: Message }) {
  return (
    <div className="msg-row msg-row--assistant">
      <div className="msg-avatar">
        <img src={mascot} alt="" />
      </div>
      <div className="msg-assistant-content">
        {message.mediaItems && message.mediaItems.length > 0 ? <MediaGallery items={message.mediaItems} /> : null}
        {message.content ? <MarkdownRenderer content={message.content} /> : null}
        {message.isStreaming ? <span className="msg-cursor" /> : null}
        {message.fileItems && message.fileItems.length > 0 ? <FileCards items={message.fileItems} /> : null}
        {message.usageSummary ? (
          <div className="msg-usage">
            tokens: {message.usageSummary.total_tokens}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function SystemMessageRow({ message }: { message: Message }) {
  if (message.fileItems && message.fileItems.length > 0) {
    return (
      <div className="msg-row msg-row--assistant">
        <div className="msg-avatar"><img src={mascot} alt="" /></div>
        <div className="msg-assistant-content"><FileCards items={message.fileItems} /></div>
      </div>
    );
  }
  if (!message.content) return null;
  return <div className="msg-system">{message.content}</div>;
}

/* ---------- 时间线 ---------- */

type TimelineItem =
  | { kind: 'message'; key: string; time: number; message: Message }
  | { kind: 'tool'; key: string; time: number; exec: ToolExecution }
  | { kind: 'reasoning'; key: string; time: number; segments: ReasoningSegment[] };

function parseTime(value: string | undefined): number {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

export function MessageList({
  sessionId,
  onSubmitAnswer,
  onSkipQuestion,
  onDismissQuestion,
}: {
  sessionId: string;
  onSubmitAnswer: (requestId: string, answers: UserAnswer[]) => void;
  onSkipQuestion: () => void;
  onDismissQuestion: () => void;
}) {
  const runtime = useChatStore((s) => s.runtimes[sessionId]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);

  const timeline = useMemo<TimelineItem[]>(() => {
    if (!runtime) return [];
    const items: TimelineItem[] = [];
    runtime.messages.forEach((message) => {
      items.push({
        kind: 'message',
        key: message.renderKey ?? message.id,
        time: parseTime(message.timestamp),
        message,
      });
    });
    runtime.toolExecutionOrder.forEach((toolCallId) => {
      const exec = runtime.toolExecutions.get(toolCallId);
      if (!exec) return;
      items.push({
        kind: 'tool',
        key: `tool-${toolCallId}`,
        time: parseTime(exec.startedAt),
        exec,
      });
    });
    if (runtime.reasoningSegments.length > 0) {
      const first = runtime.reasoningSegments[0];
      items.push({
        kind: 'reasoning',
        key: 'reasoning-current',
        time: first.startedAt || Date.now(),
        segments: runtime.reasoningSegments,
      });
    }
    items.sort((a, b) => a.time - b.time);
    return items;
  }, [runtime]);

  const messagesCount = runtime?.messages.length ?? 0;
  const streaming = runtime?.messages.some((m) => m.isStreaming) ?? false;
  const thinking = runtime?.isThinking ?? false;
  const error = runtime?.executionError ?? runtime?.error ?? null;
  const pendingQuestion = runtime?.pendingQuestion ?? null;

  // 自动滚动到底部（用户上翻时暂停）
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !stickToBottomRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [timeline, thinking, pendingQuestion]);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    stickToBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  };

  return (
    <div className="chat-scroll" ref={scrollRef} onScroll={handleScroll}>
      <div className="chat-column">
        {timeline.map((item) => {
          if (item.kind === 'tool') {
            return <ToolStatusLine key={item.key} exec={item.exec} />;
          }
          if (item.kind === 'reasoning') {
            return <ReasoningBlock key={item.key} segments={item.segments} />;
          }
          const { message } = item;
          if (message.role === 'user') return <UserMessageRow key={item.key} message={message} />;
          if (message.role === 'assistant') return <AssistantMessageRow key={item.key} message={message} />;
          return <SystemMessageRow key={item.key} message={message} />;
        })}

        {thinking && !streaming ? (
          <div className="msg-row msg-row--assistant">
            <div className="msg-avatar"><img src={mascot} alt="" /></div>
            <div className="msg-thinking">
              <Loader2 size={14} className="spin" />
              <span>正在思考…</span>
            </div>
          </div>
        ) : null}

        {error ? (
          <div className="chat-error">
            <AlertCircle size={14} />
            <span>{error}</span>
          </div>
        ) : null}

        {pendingQuestion ? (
          <AskUserQuestionCard
            payload={pendingQuestion}
            onSubmit={(answers) => onSubmitAnswer(pendingQuestion.request_id, answers)}
            onSkip={onSkipQuestion}
            onDismiss={onDismissQuestion}
          />
        ) : null}

        {messagesCount === 0 && !thinking ? (
          <div className="chat-empty">
            <img src={mascot} alt="" className="chat-empty-mascot" />
            <div className="chat-empty-text">开始新的对话吧</div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
