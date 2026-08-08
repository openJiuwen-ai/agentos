import { describe, expect, test } from 'vitest';
import { findJobIdFromCronSessionId, isCronSessionId } from './cronSessionId';

describe('isCronSessionId', () => {
  test('cron_ 前缀 → true', () => {
    expect(isCronSessionId('cron_18f2a3_proactive-tick')).toBe(true);
  });

  test('非 cron 前缀 → false', () => {
    expect(isCronSessionId('sess_abc_123')).toBe(false);
  });

  test('空 / null / undefined → false', () => {
    expect(isCronSessionId('')).toBe(false);
    expect(isCronSessionId(null)).toBe(false);
    expect(isCronSessionId(undefined)).toBe(false);
  });
});

describe('findJobIdFromCronSessionId', () => {
  const jobIds = ['abc123def456', 'proactive-tick'];

  test('后缀匹配 job_id → 返回该 job_id', () => {
    expect(findJobIdFromCronSessionId('cron_18f2a3_abc123def456', jobIds)).toBe('abc123def456');
    expect(findJobIdFromCronSessionId('cron_1a2b_proactive-tick', jobIds)).toBe('proactive-tick');
  });

  test('cron 会话但无匹配 job → null', () => {
    expect(findJobIdFromCronSessionId('cron_18f2a3_unknownjob', jobIds)).toBeNull();
  });

  test('非 cron 会话 → null(即使后缀巧合)', () => {
    expect(findJobIdFromCronSessionId('sess_abc123def456', jobIds)).toBeNull();
  });

  test('空 jobIds → null', () => {
    expect(findJobIdFromCronSessionId('cron_18f2a3_abc123def456', [])).toBeNull();
  });

  test('空 session_id → null', () => {
    expect(findJobIdFromCronSessionId('', jobIds)).toBeNull();
  });
});
