/**
 * cron 表达式校验与字段解析 — Phase 0 契约层
 *
 * 语义对齐后端 jiuwenswarm/gateway/cron/cron_expr.py:
 * 后端 normalize_cron_expr 接受 5 段(分 时 日 月 周)或 7 段(Quartz:秒 分 时 日 月 周 年),
 * 5 段自动补 "0 *"(秒=0、年=*)。前端校验器同步放宽为 5 或 7 段,
 * 比 jiuwenswarm 原版(仅 7 段)更松,与后端一致。
 *
 * 说明:仅做语法/范围校验(对应后端 validate_cron_expression 的语法部分),
 * 不引入 croniter;后端是最终权威。步长仅要求 >0(不限整除),
 * 与后端 croniter 一致(jiuwenswarm 前端原版的 stepDivisor 整除约束会误杀"每 7 分钟"等合法步长,已去除)。
 * 纯函数,便于单测。
 */

import type { CronJobDTO, CronJobEditInput } from '../types/cron';

export const DEFAULT_CRON_TIMEZONE = 'Asia/Shanghai';
export const DEFAULT_CRON_TARGET = 'web';
export const DEFAULT_WAKE_OFFSET_SECONDS = 300;

/** 字段计数(按空白分隔,过滤空段) */
export function cronFieldCount(expr: string): number {
  return String(expr ?? '')
    .trim()
    .split(/\s+/)
    .filter(p => p.length > 0).length;
}

/**
 * 把 5 段标准 cron 规范为 7 段 Quartz(镜像后端 normalize_cron_expr)。
 * 5 段 → `0 {expr} *`;7 段原样;其他段数抛错。
 */
export function normalizeCronExpr(raw: string): string {
  const s = String(raw ?? '').trim();
  const n = cronFieldCount(s);
  if (n === 5) return `0 ${s} *`;
  if (n === 7) return s;
  throw new Error(`cron_expr 必须为 5 段(分 时 日 月 周)或 7 段(秒 分 时 日 月 周 年),当前 ${n} 段`);
}

export type CronValidationResult = { valid: true } | { valid: false; reason: string };

interface FieldSpec {
  name: string;
  min: number;
  max: number;
  /** 是否允许 '?'(Quartz 日/周互斥占位) */
  allowQuestion: boolean;
}

// 5 段:[分 时 日 月 周]
const FIVE_FIELD_SPECS: readonly FieldSpec[] = [
  { name: 'minute', min: 0, max: 59, allowQuestion: false },
  { name: 'hour', min: 0, max: 23, allowQuestion: false },
  { name: 'day', min: 1, max: 31, allowQuestion: true },
  { name: 'month', min: 1, max: 12, allowQuestion: false },
  { name: 'dow', min: 1, max: 7, allowQuestion: true },
];

// 7 段 Quartz:[秒 分 时 日 月 周 年]
const SEVEN_FIELD_SPECS: readonly FieldSpec[] = [
  { name: 'second', min: 0, max: 59, allowQuestion: false },
  { name: 'minute', min: 0, max: 59, allowQuestion: false },
  { name: 'hour', min: 0, max: 23, allowQuestion: false },
  { name: 'day', min: 1, max: 31, allowQuestion: true },
  { name: 'month', min: 1, max: 12, allowQuestion: false },
  { name: 'dow', min: 1, max: 7, allowQuestion: true },
  { name: 'year', min: 1970, max: 2099, allowQuestion: false },
];

function isValidCronRange(range: string, min: number, max: number): boolean {
  const idx = range.indexOf('-');
  if (idx <= 0) return false;
  const startStr = range.slice(0, idx);
  const endStr = range.slice(idx + 1);
  if (startStr === '' || endStr === '' || endStr.includes('-')) return false;
  const start = parseInt(startStr, 10);
  const end = parseInt(endStr, 10);
  if (Number.isNaN(start) || Number.isNaN(end)) return false;
  if (start < min || end > max || start > end) return false;
  return true;
}

function isValidCronField(value: string, spec: FieldSpec): boolean {
  if (value === '*') return true;
  if (spec.allowQuestion && value === '?') return true;
  const parts = value.split(',');
  for (const part of parts) {
    if (part.includes('/')) {
      const slashIdx = part.indexOf('/');
      const range = part.slice(0, slashIdx);
      const stepStr = part.slice(slashIdx + 1);
      if (stepStr === '') return false;
      const step = parseInt(stepStr, 10);
      if (Number.isNaN(step) || step <= 0) return false;
      if (range !== '*' && !isValidCronRange(range, spec.min, spec.max)) return false;
    } else if (part.includes('-')) {
      if (!isValidCronRange(part, spec.min, spec.max)) return false;
    } else {
      const num = parseInt(part, 10);
      if (Number.isNaN(num) || num < spec.min || num > spec.max) return false;
    }
  }
  return true;
}

/**
 * 校验 cron 表达式(5 段或 7 段)。返回结构化结果;UI 可映射 i18n(Phase 3)。
 */
export function validateCronExpr(expr: string): CronValidationResult {
  const parts = String(expr ?? '')
    .trim()
    .split(/\s+/)
    .filter(p => p.length > 0);
  if (parts.length === 0) return { valid: false, reason: 'cron 表达式为空' };

  const specs = parts.length === 5 ? FIVE_FIELD_SPECS : parts.length === 7 ? SEVEN_FIELD_SPECS : null;
  if (!specs) {
    return { valid: false, reason: `需 5 段或 7 段,当前 ${parts.length} 段` };
  }
  for (let i = 0; i < parts.length; i += 1) {
    if (!isValidCronField(parts[i], specs[i])) {
      return { valid: false, reason: `${specs[i].name} 字段非法:${parts[i]}` };
    }
  }
  return { valid: true };
}

/** 读取规范化 cron_expr(后端无 schedule 子对象,直接取 cron_expr) */
export function resolveCronExpr(job: Pick<CronJobDTO, 'cron_expr'>): string {
  return (job.cron_expr ?? '').trim();
}

/** 读取时区,空值兜底默认时区 */
export function resolveTimezone(job: Pick<CronJobDTO, 'timezone'>): string {
  return (job.timezone ?? '').trim() || DEFAULT_CRON_TIMEZONE;
}

/** 读取描述(后端无 payload 子对象,直接取 description) */
export function resolveDescription(job: Pick<CronJobDTO, 'description'>): string {
  return (job.description ?? '').trim();
}

/** 读取推送频道,空值兜底 'web'(对齐后端 normalize 默认) */
export function resolveTargets(job: Pick<CronJobDTO, 'targets'>): string {
  return (job.targets ?? '').trim() || DEFAULT_CRON_TARGET;
}

/** 把 DTO 规范成编辑表单输入(裁剪、补默认值、类型收敛)。只回填基本字段。 */
export function normalizeJobForEdit(job: CronJobDTO): CronJobEditInput {
  return {
    id: job.id,
    name: (job.name ?? '').trim(),
    enabled: Boolean(job.enabled),
    cron_expr: resolveCronExpr(job),
    timezone: resolveTimezone(job),
    wake_offset_seconds: Number.isFinite(job.wake_offset_seconds) ? Math.max(0, Math.trunc(job.wake_offset_seconds)) : DEFAULT_WAKE_OFFSET_SECONDS,
    description: resolveDescription(job),
    targets: resolveTargets(job),
    created_at: job.created_at ?? null,
    updated_at: job.updated_at ?? null,
  };
}
