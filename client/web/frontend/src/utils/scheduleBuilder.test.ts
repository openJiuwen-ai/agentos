import { describe, expect, it } from 'vitest';
import {
  clampDayOfMonth,
  clampHour,
  clampMinute,
  clampMonth,
  defaultPeriodConfig,
  formatHourMinute,
  normalizeWeekdays,
  periodToCron,
  scheduleBuilderValueFromCron,
  tryParsePeriod,
  type PeriodConfig,
} from './scheduleBuilder';

describe('clampHour', () => {
  it('clamps into 0-23', () => {
    expect(clampHour(-1)).toBe(0);
    expect(clampHour(0)).toBe(0);
    expect(clampHour(9)).toBe(9);
    expect(clampHour(23)).toBe(23);
    expect(clampHour(24)).toBe(23);
  });
  it('treats NaN as 0', () => {
    expect(clampHour(Number.NaN)).toBe(0);
  });
});

describe('clampMinute', () => {
  it('clamps into 0-59', () => {
    expect(clampMinute(-5)).toBe(0);
    expect(clampMinute(30)).toBe(30);
    expect(clampMinute(59)).toBe(59);
    expect(clampMinute(60)).toBe(59);
  });
});

describe('clampDayOfMonth / clampMonth', () => {
  it('clamps day into 1-31', () => {
    expect(clampDayOfMonth(0)).toBe(1);
    expect(clampDayOfMonth(15)).toBe(15);
    expect(clampDayOfMonth(31)).toBe(31);
    expect(clampDayOfMonth(32)).toBe(31);
  });
  it('clamps month into 1-12', () => {
    expect(clampMonth(0)).toBe(1);
    expect(clampMonth(6)).toBe(6);
    expect(clampMonth(12)).toBe(12);
    expect(clampMonth(13)).toBe(12);
  });
});

describe('normalizeWeekdays', () => {
  it('dedupes and sorts', () => {
    expect(normalizeWeekdays([5, 1, 3, 1])).toEqual([1, 3, 5]);
  });
  it('filters out-of-range', () => {
    expect(normalizeWeekdays([0, 8, 2, 9])).toEqual([2]);
  });
  it('returns empty for all-invalid', () => {
    expect(normalizeWeekdays([0, 8])).toEqual([]);
  });
});

describe('formatHourMinute', () => {
  it('zero-pads both', () => {
    expect(formatHourMinute(9, 5)).toBe('09:05');
    expect(formatHourMinute(0, 0)).toBe('00:00');
    expect(formatHourMinute(23, 59)).toBe('23:59');
  });
  it('clamps before formatting', () => {
    expect(formatHourMinute(25, 70)).toBe('23:59');
  });
});

describe('periodToCron', () => {
  it('daily -> min hr * * *', () => {
    const cfg: PeriodConfig = { frequency: 'daily', hour: 8, minute: 0, weekdays: [1], dayOfMonth: 1, month: 1 };
    expect(periodToCron(cfg)).toBe('0 8 * * *');
  });
  it('weekly -> min hr * * <sorted weekdays>', () => {
    const cfg: PeriodConfig = { frequency: 'weekly', hour: 17, minute: 0, weekdays: [5], dayOfMonth: 1, month: 1 };
    expect(periodToCron(cfg)).toBe('0 17 * * 5');
  });
  it('weekly sorts and dedupes weekdays', () => {
    const cfg: PeriodConfig = { frequency: 'weekly', hour: 9, minute: 30, weekdays: [5, 1, 3], dayOfMonth: 1, month: 1 };
    expect(periodToCron(cfg)).toBe('30 9 * * 1,3,5');
  });
  it('weekly with no weekdays falls back to every-day dow', () => {
    const cfg: PeriodConfig = { frequency: 'weekly', hour: 9, minute: 0, weekdays: [], dayOfMonth: 1, month: 1 };
    expect(periodToCron(cfg)).toBe('0 9 * * *');
  });
  it('monthly -> min hr dom * *', () => {
    const cfg: PeriodConfig = { frequency: 'monthly', hour: 10, minute: 15, weekdays: [1], dayOfMonth: 20, month: 1 };
    expect(periodToCron(cfg)).toBe('15 10 20 * *');
  });
  it('yearly -> min hr dom mon *', () => {
    const cfg: PeriodConfig = { frequency: 'yearly', hour: 0, minute: 0, weekdays: [1], dayOfMonth: 1, month: 1 };
    expect(periodToCron(cfg)).toBe('0 0 1 1 *');
  });
});

describe('tryParsePeriod', () => {
  it('parses daily', () => {
    expect(tryParsePeriod('0 8 * * *')).toEqual({
      frequency: 'daily',
      hour: 8,
      minute: 0,
      weekdays: [1],
      dayOfMonth: 1,
      month: 1,
    });
  });
  it('parses weekly single weekday', () => {
    expect(tryParsePeriod('0 18 * * 5')?.frequency).toBe('weekly');
    expect(tryParsePeriod('0 18 * * 5')?.weekdays).toEqual([5]);
  });
  it('parses weekly weekday list', () => {
    expect(tryParsePeriod('30 8 * * 1-5')?.weekdays).toEqual([1, 2, 3, 4, 5]);
  });
  it('parses monthly', () => {
    expect(tryParsePeriod('0 10 15 * *')).toEqual({
      frequency: 'monthly',
      hour: 10,
      minute: 0,
      weekdays: [1],
      dayOfMonth: 15,
      month: 1,
    });
  });
  it('returns null for complex expr (step hours)', () => {
    expect(tryParsePeriod('0 */6 * * 1-5')).toBeNull();
  });
  it('returns null for 7-field', () => {
    expect(tryParsePeriod('0 0 8 * * * *')).toBeNull();
  });
  it('returns null for empty', () => {
    expect(tryParsePeriod('')).toBeNull();
  });
});

describe('scheduleBuilderValueFromCron', () => {
  it('recognizable cron -> parsed period', () => {
    const v = scheduleBuilderValueFromCron('0 18 * * 5');
    expect(v.frequency).toBe('weekly');
    expect(v.weekdays).toEqual([5]);
  });
  it('complex cron -> default period fallback', () => {
    expect(scheduleBuilderValueFromCron('0 */6 * * 1-5')).toEqual(defaultPeriodConfig());
  });
  it('empty cron -> default period (daily)', () => {
    expect(scheduleBuilderValueFromCron('').frequency).toBe('daily');
  });
});
