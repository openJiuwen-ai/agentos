/**
 * 输入框 —— 按 UI_design 对话-首页 / Agent反问用户 / 工作-PPT生成中 设计稿实现
 * 首页变体：灰底外框 + 白底内框 + 下方项目空间/权限按钮
 * 对话变体：白底圆角卡片 + 技能/模式/权限 chips + 发送/停止按钮
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { X, Box, ListOrdered, Bot } from 'lucide-react';
import type { AgentMode, MediaItem, Permission } from '../../types';
import { useChatStore, useGoalStore, useSessionStore } from '../../stores';
import { PlusMenu, ModelSelector, PermissionSelector, SkillSelector, ProjectSelector } from './popups';
import sendDefaultIcon from '../../assets/design/send-default.png';
import sendActiveIcon from '../../assets/design/send-active.png';
import stopCircleIcon from '../../assets/design/stop-circle.png';
import './Composer.css';

const PLACEHOLDER = '需要帮你做些什么？输入“/”快速引用技能及指令';

export interface ComposerProps {
  sessionId: string;
  variant: 'home' | 'chat';
  isProcessing: boolean;
  disabled?: boolean;
  permission: Permission;
  onChangePermission: (permission: Permission) => void;
  onSend: (content: string, mediaItems?: MediaItem[]) => void;
  onCancel: () => void;
  onSchedule: (draftText: string) => void;
  mode: AgentMode;
  onSwitchMode: (mode: AgentMode) => void;
  focusKey?: string;
}

function fileToMediaItem(file: File): Promise<MediaItem> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('读取文件失败'));
    reader.onload = () => {
      const dataUrl = String(reader.result ?? '');
      const base64 = dataUrl.includes(',') ? dataUrl.slice(dataUrl.indexOf(',') + 1) : dataUrl;
      const mime = file.type || 'application/octet-stream';
      const type: MediaItem['type'] = mime.startsWith('image/')
        ? 'image'
        : mime.startsWith('audio/')
          ? 'audio'
          : mime.startsWith('video/')
            ? 'video'
            : 'document';
      resolve({
        type,
        mimeType: mime,
        filename: file.name,
        base64Data: base64,
        sizeBytes: file.size,
      });
    };
    reader.readAsDataURL(file);
  });
}

export function Composer({
  sessionId, variant, isProcessing, disabled, permission, onChangePermission,
  onSend, onCancel, onSchedule, mode, onSwitchMode, focusKey,
}: ComposerProps) {
  const inputValue = useChatStore((s) => s.runtimes[sessionId]?.inputValue ?? '');
  const setInputValue = useChatStore((s) => s.setInputValue);
  const taskQueue = useChatStore((s) => s.runtimes[sessionId]?.taskQueue ?? []);
  const clearTaskQueue = useChatStore((s) => s.clearTaskQueue);
  const selectedSkills = useSessionStore((s) => s.runtimes[sessionId]?.selectedSkills ?? []);
  const removeSelectedSkill = useSessionStore((s) => s.removeSelectedSkill);
  const goalArmed = useGoalStore((s) => s.runtimes[sessionId]?.armed ?? false);
  const setGoalArmed = useGoalStore((s) => s.setArmed);

  const [attachments, setAttachments] = useState<MediaItem[]>([]);
  const [skillMenuOpen, setSkillMenuOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const skillMenuAnchorRef = useRef<HTMLButtonElement>(null);

  // 自动增高
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, variant === 'home' ? 220 : 180)}px`;
  }, [inputValue, variant]);

  // 聚焦
  useEffect(() => {
    if (focusKey) textareaRef.current?.focus();
  }, [focusKey]);

  const canSend = !disabled && (inputValue.trim().length > 0 || attachments.length > 0);

  const handleSend = useCallback(() => {
    const content = inputValue;
    if (!content.trim() && attachments.length === 0) return;
    if (disabled) return;
    const mediaItems = attachments.length > 0 ? attachments : undefined;
    setAttachments([]);
    onSend(content, mediaItems);
  }, [inputValue, attachments, disabled, onSend]);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (isProcessing) return;
      handleSend();
    }
  };

  const handleFiles = async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (list.length === 0) return;
    try {
      const items = await Promise.all(list.map(fileToMediaItem));
      setAttachments((prev) => [...prev, ...items]);
    } catch {
      /* 读取失败忽略 */
    }
  };

  const handlePaste = (event: React.ClipboardEvent) => {
    const files = Array.from(event.clipboardData?.files ?? []);
    if (files.length > 0) {
      event.preventDefault();
      void handleFiles(files);
    }
  };

  const composerBody = (
    <>
      {/* 附件预览 */}
      {attachments.length > 0 ? (
        <div className="composer-attachments">
          {attachments.map((item, index) => (
            <div key={`${item.filename}-${index}`} className="composer-attachment">
              {item.type === 'image' && item.base64Data ? (
                <img
                  src={`data:${item.mimeType};base64,${item.base64Data}`}
                  alt={item.filename}
                  className="composer-attachment-img"
                />
              ) : (
                <span className="composer-attachment-name">{item.filename}</span>
              )}
              <button
                className="composer-attachment-remove"
                onClick={() => setAttachments((prev) => prev.filter((_, i) => i !== index))}
              >
                <X size={11} />
              </button>
            </div>
          ))}
        </div>
      ) : null}

      {/* 已选技能 chips */}
      {selectedSkills.length > 0 ? (
        <div className="composer-skills">
          {selectedSkills.map((skill) => (
            <span key={skill} className="skill-chip">
              <Box size={12} />
              <span>{skill}</span>
              <button onClick={() => removeSelectedSkill(sessionId, skill)}><X size={11} /></button>
            </span>
          ))}
        </div>
      ) : null}

      {/* 目标徽章 */}
      {goalArmed ? (
        <div className="composer-skills">
          <span className="skill-chip skill-chip--goal">
            <span>将设为持续目标</span>
            <button onClick={() => setGoalArmed(sessionId, false)}><X size={11} /></button>
          </span>
        </div>
      ) : null}

      <textarea
        ref={textareaRef}
        className="composer-textarea"
        placeholder={PLACEHOLDER}
        value={inputValue}
        rows={variant === 'home' ? 3 : 2}
        onChange={(e) => setInputValue(sessionId, e.target.value)}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
      />

      <div className="composer-bottom">
        <div className="composer-bottom-left">
          <PlusMenu
            sessionId={sessionId}
            goalArmed={goalArmed}
            onPickFiles={() => fileInputRef.current?.click()}
            onSchedule={() => onSchedule(inputValue)}
            onToggleGoal={() => setGoalArmed(sessionId, !goalArmed)}
            onOpenSkills={() => setSkillMenuOpen(true)}
          />
          {variant === 'chat' ? (
            <>
              <button
                className="composer-chip"
                title="切换模式"
                onClick={() => onSwitchMode(mode === 'team' ? 'agent' : 'team')}
              >
                <Bot size={14} />
                <span>{mode === 'team' ? '团队模式' : '单Agent模式'}</span>
              </button>
              <PermissionSelector permission={permission} onChange={onChangePermission} />
              <button
                ref={skillMenuAnchorRef}
                className="composer-chip"
                onClick={() => setSkillMenuOpen(true)}
              >
                <Box size={14} />
                <span>技能</span>
              </button>
            </>
          ) : null}
        </div>
        <div className="composer-bottom-right">
          <ModelSelector sessionId={sessionId} />
          {isProcessing ? (
            <button className="composer-send" title="停止" onClick={onCancel}>
              <img src={stopCircleIcon} alt="停止" />
            </button>
          ) : (
            <button
              className="composer-send"
              title="发送"
              disabled={!canSend}
              onClick={handleSend}
            >
              <img src={canSend ? sendActiveIcon : sendDefaultIcon} alt="发送" />
            </button>
          )}
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        style={{ display: 'none' }}
        onChange={(e) => {
          if (e.target.files) void handleFiles(e.target.files);
          e.target.value = '';
        }}
      />
      <SkillSelector
        sessionId={sessionId}
        open={skillMenuOpen}
        onClose={() => setSkillMenuOpen(false)}
        anchorRef={skillMenuAnchorRef}
      />
    </>
  );

  if (variant === 'home') {
    return (
      <div className="composer-home-wrap">
        <div className="composer-outer">
          <div className="composer-inner">{composerBody}</div>
          <div className="composer-home-selectors">
            <ProjectSelector />
            <PermissionSelector permission={permission} onChange={onChangePermission} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="composer-chat-wrap">
      {taskQueue.length > 0 ? (
        <div className="composer-queue">
          <ListOrdered size={14} />
          <span>{taskQueue.length} 条消息排队中</span>
          <button onClick={() => clearTaskQueue(sessionId)}>清空</button>
        </div>
      ) : null}
      <div className="composer-chat-card">{composerBody}</div>
    </div>
  );
}
