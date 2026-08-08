/**
 * 调度构建器合成逻辑 — 纯函数,便于单测。
 *
 * 把 ScheduleBuilder UI 的"周期 + 时间"配置合成成 5 段标准 cron
 * (分 时 日 月 周;周 1=周一..7=周日),后端 normalize 为 7 段 Quartz。
 * 与 utils/cronLabel.ts(cronToScheduleLabel)同一字段语义,实时预览复用它(DRY)。
 *
 * 周期(对齐设计稿"执行频率"区"执行周期";问题修复轮决策 ① period-only):
 *   每天 / 每周(周几 multi) / 每月(几号) / 每年(月+日)+ 时间(HH:mm)。
 *   原按间隔 / 单次 / Cron表达式 三种模式已废弃删除。
 */

export type PeriodFrequency = 'daily' | 'weekly' | 'monthly' | 'yearly';

/** 周几:1=周一..7=周日(与 cron dow、cronLabel.ts 一致) */
export type Weekday = 1 | 2 | 3 | 4 | 5 | 6 | 7;

export interface PeriodConfig {
  frequency: PeriodFrequency;
  hour: number; // 0-23
  minute: number; // 0-59
  /** weekly:选中的周几(1..7);其余频率忽略 */
  weekdays: Weekday[];
  /** monthly / yearly:几号 1-31 */
  dayOfMonth: number;
  /** yearly:几月 1-12 */
  month: number;
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

/** 规范化小时(0-23),非法→0 */
export function clampHour(n: number): number {
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(23, Math.trunc(n)));
}

/** 规范化分钟(0-59),非法→0 */
export function clampMinute(n: number): number {
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(59, Math.trunc(n)));
}

/** 规范化日(1-31),非法→1 */
export function clampDayOfMonth(n: number): number {
  if (!Number.isFinite(n)) return 1;
  return Math.max(1, Math.min(31, Math.trunc(n)));
}

/** 规范化月(1-12),非法→1 */
export function clampMonth(n: number): number {
  if (!Number.isFinite(n)) return 1;
  return Math.max(1, Math.min(12, Math.trunc(n)));
}

/** 规范化周几列表:去重 + 排序,过滤越界 */
export function normalizeWeekdays(weekdays: readonly number[]): Weekday[] {
  const set = new Set<number>();
  for (const w of weekdays) {
    if (Number.isInteger(w) && w >= 1 && w <= 7) set.add(w);
  }
  return Array.from(set).sort((a, b) => a - b) as Weekday[];
}

/** "HH:mm" 形态(供 time input 的 value) */
export function formatHourMinute(hour: number, minute: number): string {
  return `${pad2(clampHour(hour))}:${pad2(clampMinute(minute))}`;
}

/**
 * 周期配置 → 5 段 cron。
 * weekly 至少 1 个周几(调用方保证;空则按每天处理避免空串)。
 */
export function periodToCron(cfg: PeriodConfig): string {
  const min = clampMinute(cfg.minute);
  const hr = clampHour(cfg.hour);
  switch (cfg.frequency) {
    case 'daily':
      return `${min} ${hr} * * *`;
    case 'weekly': {
      const days = normalizeWeekdays(cfg.weekdays);
      const dow = days.length > 0 ? days.join(',') : '*';
      return `${min} ${hr} * * ${dow}`;
    }
    case 'monthly': {
      const dom = clampDayOfMonth(cfg.dayOfMonth);
      return `${min} ${hr} ${dom} * *`;
    }
    case 'yearly': {
      const dom = clampDayOfMonth(cfg.dayOfMonth);
      const mon = clampMonth(cfg.month);
      return `${min} ${hr} ${dom} ${mon} *`;
    }
    default:
      return '';
  }
}

/** 默认 PeriodConfig:每天 09:00 */
export function defaultPeriodConfig(): PeriodConfig {
  return { frequency: 'daily', hour: 9, minute: 0, weekdays: [1], dayOfMonth: 1, month: 1 };
}

function expandRange(range: string): number[] {
  const idx = range.indexOf('-');
  if (idx <= 0) return [];
  const start = parseInt(range.slice(0, idx), 10);
  const end = parseInt(range.slice(idx + 1), 10);
  if (!Number.isInteger(start) || !Number.isInteger(end) || start > end) return [];
  const out: number[] = [];
  for (let i = start; i <= end; i += 1) out.push(i);
  return out;
}

/**
 * 尽力把 5 段 cron 反解成 PeriodConfig(供编辑/模板预填)。无法识别返回 null(调用方回退默认)。
 * 仅覆盖简单单时刻模式:每天 / 每周(周几列表或工作日) / 每月(几号)。
 */
export function tryParsePeriod(expr: string): PeriodConfig | null {
  const parts = String(expr ?? '')
    .trim()
    .split(/\s+/)
    .filter(p => p.length > 0);
  if (parts.length !== 5) return null;
  const [minF, hrF, domF, monF, dowF] = parts;
  if (!/^\d+$/.test(minF) || !/^\d+$/.test(hrF)) return null;
  const minute = parseInt(minF, 10);
  const hour = parseInt(hrF, 10);
  if (minute < 0 || minute > 59 || hour < 0 || hour > 23) return null;

  const domWild = domF === '*' || domF === '?';
  const monWild = monF === '*' || monF === '?';
  const dowWild = dowF === '*' || dowF === '?';

  // 每天:* * * *
  if (domWild && monWild && dowWild) {
    return { frequency: 'daily', hour, minute, weekdays: [1], dayOfMonth: 1, month: 1 };
  }
  // 每周:dom=* mon=* dow=列表
  if (domWild && monWild && !dowWild) {
    const weekdays = normalizeWeekdays(dowF.split(',').flatMap(s => (s.includes('-') ? expandRange(s) : [parseInt(s, 10)])));
    if (weekdays.length === 0) return null;
    return { frequency: 'weekly', hour, minute, weekdays, dayOfMonth: 1, month: 1 };
  }
  // 每月:dom=数字 mon=* dow=*
  if (!domWild && monWild && dowWild && /^\d+$/.test(domF)) {
    return { frequency: 'monthly', hour, minute, weekdays: [1], dayOfMonth: parseInt(domF, 10), month: 1 };
  }
  return null;
}

/**
 * 由初始 cronExpr 推断 PeriodConfig(编辑/模板预填用)。
 * 能反解 → 原配置;否则 → 默认(每天 09:00)。
 */
export function scheduleBuilderValueFromCron(expr: string): PeriodConfig {
  return tryParsePeriod(String(expr ?? '').trim()) ?? defaultPeriodConfig();
}
