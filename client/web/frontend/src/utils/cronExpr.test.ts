import { describe, it, expect } from 'vitest';
import {
  cronFieldCount,
  normalizeCronExpr,
  validateCronExpr,
  resolveCronExpr,
  resolveTimezone,
  resolveDescription,
  resolveTargets,
  normalizeJobForEdit,
  DEFAULT_CRON_TIMEZONE,
  DEFAULT_CRON_TARGET,
  DEFAULT_WAKE_OFFSET_SECONDS,
} from './cronExpr';
import type { CronJobDTO } from '../types/cron';

describe('cronFieldCount', () => {
  it('returns 5 for a standard 5-field expression', () => {
    expect(cronFieldCount('0 17 * * 5')).toBe(5);
  });
  it('returns 7 for a Quartz 7-field expression', () => {
    expect(cronFieldCount('0 0 17 * * 5 *')).toBe(7);
  });
  it('returns 0 for empty or whitespace-only input', () => {
    expect(cronFieldCount('')).toBe(0);
    expect(cronFieldCount('   ')).toBe(0);
  });
  it('collapses extra whitespace between fields', () => {
    expect(cronFieldCount('  0   17   *  ')).toBe(3);
  });
});

describe('normalizeCronExpr', () => {
  it('prepends second=0 and appends year=* for 5-field input', () => {
    expect(normalizeCronExpr('0 17 * * 5')).toBe('0 0 17 * * 5 *');
  });
  it('leaves a 7-field Quartz expression unchanged', () => {
    const seven = '0 0 17 ? * 5 *';
    expect(normalizeCronExpr(seven)).toBe(seven);
  });
  it('throws on a 6-field expression', () => {
    expect(() => normalizeCronExpr('0 17 * * 5 2025')).toThrow();
  });
  it('throws on empty input', () => {
    expect(() => normalizeCronExpr('')).toThrow();
  });
});

describe('validateCronExpr', () => {
  it('accepts a 5-field weekly schedule', () => {
    expect(validateCronExpr('0 17 * * 5')).toEqual({ valid: true });
  });
  it('accepts a 5-field daily schedule', () => {
    expect(validateCronExpr('0 9 * * *')).toEqual({ valid: true });
  });
  it('accepts a 5-field weekday range', () => {
    expect(validateCronExpr('30 15 * * 1-5')).toEqual({ valid: true });
  });
  it('accepts a list of minutes', () => {
    expect(validateCronExpr('0,30 9 * * *')).toEqual({ valid: true });
  });
  it('accepts an arbitrary step like */7 (matches backend croniter)', () => {
    expect(validateCronExpr('0 */7 * * *')).toEqual({ valid: true });
  });
  it('accepts a 7-field Quartz expression', () => {
    expect(validateCronExpr('0 0 17 ? * 5 *')).toEqual({ valid: true });
  });
  it('rejects empty input', () => {
    expect(validateCronExpr('').valid).toBe(false);
  });
  it('rejects a 4-field expression and reports field count', () => {
    const r = validateCronExpr('0 17 * *');
    expect(r.valid).toBe(false);
    if (!r.valid) expect(r.reason).toContain('5');
  });
  it('rejects an out-of-range minute and names the field', () => {
    const r = validateCronExpr('60 17 * * *');
    expect(r.valid).toBe(false);
    if (!r.valid) expect(r.reason).toContain('minute');
  });
  it('rejects an out-of-range hour', () => {
    const r = validateCronExpr('0 25 * * *');
    expect(r.valid).toBe(false);
    if (!r.valid) expect(r.reason).toContain('hour');
  });
  it('rejects an out-of-range month', () => {
    expect(validateCronExpr('0 0 * 13 *').valid).toBe(false);
  });
  it('rejects an out-of-range day-of-week', () => {
    expect(validateCronExpr('0 0 * * 9').valid).toBe(false);
  });
  it('rejects a zero step', () => {
    expect(validateCronExpr('0 */0 * * *').valid).toBe(false);
  });
  it('rejects a 7-field expression with an out-of-range year and names it', () => {
    const r = validateCronExpr('0 0 17 ? * 5 1800');
    expect(r.valid).toBe(false);
    if (!r.valid) expect(r.reason).toContain('year');
  });
});

describe('resolveCronExpr', () => {
  it('trims surrounding whitespace', () => {
    expect(resolveCronExpr({ cron_expr: '  0 17 * * 5  ' })).toBe('0 17 * * 5');
  });
  it('returns empty string for an empty field', () => {
    expect(resolveCronExpr({ cron_expr: '' })).toBe('');
  });
});

describe('resolveTimezone', () => {
  it('falls back to the default timezone when empty', () => {
    expect(resolveTimezone({ timezone: '' })).toBe(DEFAULT_CRON_TIMEZONE);
  });
  it('trims a non-empty timezone', () => {
    expect(resolveTimezone({ timezone: '  UTC  ' })).toBe('UTC');
  });
});

describe('resolveDescription', () => {
  it('trims the description', () => {
    expect(resolveDescription({ description: '  hi  ' })).toBe('hi');
  });
});

describe('resolveTargets', () => {
  it('falls back to the default target when empty', () => {
    expect(resolveTargets({ targets: '' })).toBe(DEFAULT_CRON_TARGET);
  });
  it('trims a non-empty target', () => {
    expect(resolveTargets({ targets: '  feishu  ' })).toBe('feishu');
  });
});

describe('normalizeJobForEdit', () => {
  const baseJob: CronJobDTO = {
    id: 'job-1',
    name: '  Weekly Report  ',
    enabled: true,
    expired: false,
    cron_expr: '  0 17 * * 5  ',
    timezone: '  Asia/Shanghai  ',
    wake_offset_seconds: 300,
    description: '  Generate weekly report  ',
    targets: '  web  ',
    created_at: 100,
    updated_at: 200,
  };

  it('trims string fields and preserves id and timestamps', () => {
    const out = normalizeJobForEdit(baseJob);
    expect(out.name).toBe('Weekly Report');
    expect(out.cron_expr).toBe('0 17 * * 5');
    expect(out.timezone).toBe('Asia/Shanghai');
    expect(out.description).toBe('Generate weekly report');
    expect(out.targets).toBe('web');
    expect(out.id).toBe('job-1');
    expect(out.created_at).toBe(100);
    expect(out.updated_at).toBe(200);
  });

  it('coerces a truthy non-boolean enabled to a boolean', () => {
    const out = normalizeJobForEdit({ ...baseJob, enabled: 1 as unknown as boolean });
    expect(out.enabled).toBe(true);
  });

  it('clamps a negative wake_offset_seconds to 0', () => {
    const out = normalizeJobForEdit({ ...baseJob, wake_offset_seconds: -50 });
    expect(out.wake_offset_seconds).toBe(0);
  });

  it('truncates a fractional wake_offset_seconds to an integer', () => {
    const out = normalizeJobForEdit({ ...baseJob, wake_offset_seconds: 300.9 });
    expect(out.wake_offset_seconds).toBe(300);
  });

  it('falls back to the default wake_offset_seconds when not finite', () => {
    const out = normalizeJobForEdit({ ...baseJob, wake_offset_seconds: Number.NaN });
    expect(out.wake_offset_seconds).toBe(DEFAULT_WAKE_OFFSET_SECONDS);
  });

  it('normalizes null timestamps to null', () => {
    const out = normalizeJobForEdit({ ...baseJob, created_at: null, updated_at: null });
    expect(out.created_at).toBeNull();
    expect(out.updated_at).toBeNull();
  });
});
