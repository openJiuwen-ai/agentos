/**
 * cronLabel 单测 — AAA 模式。
 * 期望值取自 utils/cronTemplates.ts 的 scheduleLabel 字段 + 设计稿"每周五 17:00"等示例。
 */
import { describe, expect, it } from 'vitest';
import { cronToScheduleLabel, formatCronDateTime } from './cronLabel';

describe('cronToScheduleLabel', () => {
  describe('每天(分 时 * * *)', () => {
    it('0 18 * * * → 每天 18:00', () => {
      expect(cronToScheduleLabel('0 18 * * *')).toBe('每天 18:00');
    });
    it('0 9 * * * → 每天 09:00(补零)', () => {
      expect(cronToScheduleLabel('0 9 * * *')).toBe('每天 09:00');
    });
    it('0 8 * * * → 每天 08:00', () => {
      expect(cronToScheduleLabel('0 8 * * *')).toBe('每天 08:00');
    });
    it('0 0 * * * → 每天 00:00(午夜)', () => {
      expect(cronToScheduleLabel('0 0 * * *')).toBe('每天 00:00');
    });
  });

  describe('工作日(分 时 * * 1-5)', () => {
    it('30 15 * * 1-5 → 工作日 15:30', () => {
      expect(cronToScheduleLabel('30 15 * * 1-5')).toBe('工作日 15:30');
    });
  });

  describe('每周(分 时 * * D)', () => {
    it('0 17 * * 5 → 每周五 17:00(dow 1=周一)', () => {
      expect(cronToScheduleLabel('0 17 * * 5')).toBe('每周五 17:00');
    });
    it('0 9 * * 1 → 每周一 09:00', () => {
      expect(cronToScheduleLabel('0 9 * * 1')).toBe('每周一 09:00');
    });
    it('0 9 * * 7 → 每周日 09:00(7=周日)', () => {
      expect(cronToScheduleLabel('0 9 * * 7')).toBe('每周日 09:00');
    });
    it('0 9 * * 1,3,5 → 每周一三五 09:00(多日)', () => {
      expect(cronToScheduleLabel('0 9 * * 1,3,5')).toBe('每周一三五 09:00');
    });
  });

  describe('每月(分 时 DOM * *)', () => {
    it('0 9 1 * * → 每月 1 日 09:00', () => {
      expect(cronToScheduleLabel('0 9 1 * *')).toBe('每月 1 日 09:00');
    });
    it('30 10 15 * * → 每月 15 日 10:30', () => {
      expect(cronToScheduleLabel('30 10 15 * *')).toBe('每月 15 日 10:30');
    });
  });

  describe('间隔(步长)', () => {
    it('*/15 * * * * → 每 15 分钟', () => {
      expect(cronToScheduleLabel('*/15 * * * *')).toBe('每 15 分钟');
    });
    it('0 */2 * * * → 每 2 小时', () => {
      expect(cronToScheduleLabel('0 */2 * * *')).toBe('每 2 小时');
    });
  });

  describe('7 段 Quartz', () => {
    it('0 0 9 * * ? * → 每天 09:00(? 视为通配)', () => {
      expect(cronToScheduleLabel('0 0 9 * * ? *')).toBe('每天 09:00');
    });
    it('0 0 17 * * 5 * → 每周五 17:00', () => {
      expect(cronToScheduleLabel('0 0 17 * * 5 *')).toBe('每周五 17:00');
    });
  });

  describe('容错与回退', () => {
    it('两端空白被裁剪', () => {
      expect(cronToScheduleLabel('  0 9 * * *  ')).toBe('每天 09:00');
    });
    it('空串 → 空串', () => {
      expect(cronToScheduleLabel('')).toBe('');
    });
    it('无法识别的复杂表达式 → 原样返回', () => {
      expect(cronToScheduleLabel('2-10/3 9 * * 1,2,3')).toBe('2-10/3 9 * * 1,2,3');
    });
    it('段数非法(3 段)→ 原样返回', () => {
      expect(cronToScheduleLabel('0 9 *')).toBe('0 9 *');
    });
  });
});

describe('formatCronDateTime', () => {
  it('epoch 毫秒 → YYYY/MM/DD HH:mm(本地时区)', () => {
    // 2026-07-24 17:00 本地;用构造器固定
    const d = new Date(2026, 6, 24, 17, 0); // 月份 0 基
    expect(formatCronDateTime(d.getTime())).toBe('2026/07/24 17:00');
  });
  it('epoch 秒(<1e11)按秒解释', () => {
    const d = new Date(2026, 6, 24, 17, 0);
    expect(formatCronDateTime(Math.floor(d.getTime() / 1000))).toBe('2026/07/24 17:00');
  });
  it('ISO 字符串(含时区)→ 按本地渲染', () => {
    // 用本地时区构造以避免时区漂移
    const d = new Date(2026, 6, 24, 17, 0);
    expect(formatCronDateTime(d.toISOString())).toMatch(/^\d{4}\/\d{2}\/\d{2} \d{2}:\d{2}$/);
  });
  it('null → 空串', () => {
    expect(formatCronDateTime(null)).toBe('');
  });
  it('非法值 → 空串', () => {
    expect(formatCronDateTime('not-a-date')).toBe('');
  });
});
