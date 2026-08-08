/**
 * Session 状态 → 中文标签 — 纯函数,便于单测。
 *
 * 执行历史(Phase 4)用:把后端 SessionStatus('active'|'paused'|'completed'|'interrupted')
 * 映射为中文展示标签。执行历史无设计稿原文,文案为合理推断(交付时让用户校对)。
 */
import type { SessionStatus } from '../types';

const STATUS_LABELS: Readonly<Record<SessionStatus, string>> = {
  completed: '已完成',
  interrupted: '已中断',
  active: '进行中',
  paused: '已暂停',
};

/** 把 SessionStatus 映射为中文标签;未知值原样返回(防御后端新增状态)。 */
export function sessionStatusToLabel(status: SessionStatus): string {
  return STATUS_LABELS[status] ?? status;
}
