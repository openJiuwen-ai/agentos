import { describe, expect, test } from 'vitest';
import type { SessionStatus } from '../types';
import { sessionStatusToLabel } from './sessionStatus';

describe('sessionStatusToLabel', () => {
  test('completed → 已完成', () => {
    expect(sessionStatusToLabel('completed')).toBe('已完成');
  });

  test('interrupted → 已中断', () => {
    expect(sessionStatusToLabel('interrupted')).toBe('已中断');
  });

  test('active → 进行中', () => {
    expect(sessionStatusToLabel('active')).toBe('进行中');
  });

  test('paused → 已暂停', () => {
    expect(sessionStatusToLabel('paused')).toBe('已暂停');
  });

  test('未知状态原样返回(防御后端新增)', () => {
    expect(sessionStatusToLabel('archived' as SessionStatus)).toBe('archived');
  });
});
