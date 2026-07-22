import type { UsageOverviewResponse, UserUsageDetailResponse } from '@/api/inference';

const MS_PER_DAY = 24 * 60 * 60 * 1000;

const TOKEN_MILLION = 1_000_000;
const TOKEN_THOUSAND = 1_000;
const TOKEN_MILLION_FRACTION_DIGITS = 2;
const TOKEN_THOUSAND_FRACTION_DIGITS = 1;

const COST_FRACTION_DIGITS = 4;

/** 用于查询「累计」用量的起始日期 */
export const USAGE_ALL_TIME_START = '2000-01-01';

export function formatDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/**
 * @param daysOrStart
 *  - number: 从今天往前 N 天
 *  - string: 解析为起始日期（例如 {@link USAGE_ALL_TIME_START}）
 */
export function getDateRange(daysOrStart: number | string): { start_date: string; end_date: string } {
  const end = new Date();
  const start =
    typeof daysOrStart === 'number'
      ? new Date(Date.now() - daysOrStart * MS_PER_DAY)
      : new Date(daysOrStart);

  return { start_date: formatDate(start), end_date: formatDate(end) };
}

/** 生成 start_date 到 end_date（含）的日期序列 */
export function generateDateSeriesFromRange(startDate: string, endDate: string): string[] {
  const dates: string[] = [];
  const current = new Date(startDate);
  const end = new Date(endDate);

  while (current <= end) {
    dates.push(formatDate(current));
    current.setDate(current.getDate() + 1);
  }

  return dates;
}

export function formatTokens(tokens: number): string {
  if (tokens >= TOKEN_MILLION) {
    return (tokens / TOKEN_MILLION).toFixed(TOKEN_MILLION_FRACTION_DIGITS) + 'M';
  }
  if (tokens >= TOKEN_THOUSAND) {
    return (tokens / TOKEN_THOUSAND).toFixed(TOKEN_THOUSAND_FRACTION_DIGITS) + 'K';
  }
  return tokens.toString();
}

export function formatCost(cost: number): string {
  return '$' + cost.toFixed(COST_FRACTION_DIGITS);
}

export function calculateOverviewTotals(data: UsageOverviewResponse) {
  return (data.users ?? []).reduce(
    (acc, user) => ({
      requests: acc.requests + user.total_requests,
      tokens: acc.tokens + user.total_tokens,
    }),
    { requests: 0, tokens: 0 },
  );
}

export function calculateUserTotals(data: UserUsageDetailResponse) {
  return (data.daily_activity ?? []).reduce(
    (acc, day) => ({
      requests: acc.requests + day.requests,
      tokens: acc.tokens + day.tokens,
    }),
    { requests: 0, tokens: 0 },
  );
}
