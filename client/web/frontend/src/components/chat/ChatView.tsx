/**
 * 对话视图 —— 头部(标题) + 消息列表 + 输入框
 */
import type { AgentMode, MediaItem, Permission, UserAnswer } from '../../types';
import { Composer } from '../composer/Composer';
import { MessageList } from './MessageList';

export interface ChatViewProps {
  sessionId: string;
  title: string;
  isProcessing: boolean;
  permission: Permission;
  onChangePermission: (permission: Permission) => void;
  mode: AgentMode;
  onSwitchMode: (mode: AgentMode) => void;
  onSend: (content: string, mediaItems?: MediaItem[]) => void;
  onCancel: () => void;
  onSchedule: (draftText: string) => void;
  onSubmitAnswer: (requestId: string, answers: UserAnswer[]) => void;
  onSkipQuestion: () => void;
  onDismissQuestion: () => void;
  modelBadge?: string;
}

export function ChatView({
  sessionId, title, isProcessing, permission, onChangePermission, mode, onSwitchMode,
  onSend, onCancel, onSchedule, onSubmitAnswer, onSkipQuestion, onDismissQuestion, modelBadge,
}: ChatViewProps) {
  return (
    <div className="chat-view">
      <div className="chat-header">
        <div className="chat-header-title">{title || '新对话'}</div>
        {modelBadge ? <div className="chat-header-badge">{modelBadge}</div> : null}
      </div>
      <MessageList
        sessionId={sessionId}
        onSubmitAnswer={onSubmitAnswer}
        onSkipQuestion={onSkipQuestion}
        onDismissQuestion={onDismissQuestion}
      />
      <div className="chat-composer">
        <Composer
          sessionId={sessionId}
          variant="chat"
          isProcessing={isProcessing}
          permission={permission}
          onChangePermission={onChangePermission}
          onSend={onSend}
          onCancel={onCancel}
          onSchedule={onSchedule}
          mode={mode}
          onSwitchMode={onSwitchMode}
        />
      </div>
    </div>
  );
}
