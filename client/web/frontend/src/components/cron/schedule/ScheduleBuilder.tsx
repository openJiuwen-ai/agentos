/**
 * ScheduleBuilder — 执行频率盒内核心控件。对照设计稿"定时任务 - 创建"执行频率区。
 *
 * period-only:每个字段一行(label 左 + 值右)——
 * 执行周期(每天/每周/每月/每年)/ 时间(HH:mm)/ 生效日期区间(禁用)/ 时区。
 * weekly→周几 multi,monthly→几号,yearly→月+日。
 * 合成 5 段标准 cron(periodToCron),经 onCronChange 上抛(submit)。
 *
 * 生效日期区间:设计稿指定时任务的到期时间(如"到 2026-08-31 生效"),
 * 后端 CronJob 无此字段 → 禁用 + "敬请期待" 纯视觉(决策④)。
 * 文案硬编码设计稿原文中文。
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  clampDayOfMonth,
  clampMonth,
  normalizeWeekdays,
  periodToCron,
  scheduleBuilderValueFromCron,
  type PeriodConfig,
  type PeriodFrequency,
  type Weekday,
} from '../../../utils/scheduleBuilder';
import { TimePicker } from './TimePicker';

/** 文案严格对齐设计稿"定时任务 - 创建"原文(中文)。 */
const TEXT = {
  freqDaily: '每天',
  freqWeekly: '每周',
  freqMonthly: '每月',
  freqYearly: '每年',
  labelFrequency: '执行周期',
  labelTime: '时间',
  labelDateRange: '生效日期区间',
  labelTimezone: '时区',
  dateRangeSep: '至',
  dateRangeStartPh: '开始日期',
  dateRangeEndPh: '结束日期',
  groupWeekdays: '周几',
  domLabel: '几号',
  monthLabel: '月',
  dayLabel: '日',
} as const;

const FREQUENCY_OPTIONS: { value: PeriodFrequency; label: string }[] = [
  { value: 'daily', label: TEXT.freqDaily },
  { value: 'weekly', label: TEXT.freqWeekly },
  { value: 'monthly', label: TEXT.freqMonthly },
  { value: 'yearly', label: TEXT.freqYearly },
];

/** 周几:1=周一..7=周日(与 cron dow 一致) */
const WEEKDAY_LABELS: Readonly<Record<number, string>> = {
  1: '一',
  2: '二',
  3: '三',
  4: '四',
  5: '五',
  6: '六',
  7: '日',
};

const WEEKDAYS: readonly Weekday[] = [1, 2, 3, 4, 5, 6, 7];

const TIMEZONE_OPTIONS: readonly string[] = ['Asia/Shanghai', 'Asia/Urumqi', 'Asia/Chongqing', 'Asia/Hong_Kong', 'UTC'];

export interface ScheduleBuilderProps {
  initialCron: string;
  onCronChange: (expr: string) => void;
  timezone: string;
  onTimezoneChange: (tz: string) => void;
}

export function ScheduleBuilder({ initialCron, onCronChange, timezone, onTimezoneChange }: ScheduleBuilderProps) {
  const [period, setPeriod] = useState<PeriodConfig>(() => scheduleBuilderValueFromCron(initialCron));
  const [dateRange, setDateRange] = useState<{ start: string; end: string }>({ start: '', end: '' });
  const lastSentRef = useRef<string>('');

  // 派生 cron + 上抛(去重,避免循环)
  const derived = useMemo(() => periodToCron(period), [period]);
  useEffect(() => {
    if (derived !== lastSentRef.current) {
      lastSentRef.current = derived;
      onCronChange(derived);
    }
  }, [derived, onCronChange]);

  const patch = (p: Partial<PeriodConfig>) => setPeriod(prev => ({ ...prev, ...p }));

  const toggleWeekday = (day: Weekday) =>
    patch({
      weekdays: normalizeWeekdays(period.weekdays.includes(day) ? period.weekdays.filter(w => w !== day) : [...period.weekdays, day]),
    });

  return (
    <div className="cron-sb">
      {/* 三行:label 左 + 下拉框右 */}
      <div className="cron-drawer__setting-row">
        <span className="cron-drawer__setting-label">{TEXT.labelFrequency}</span>
        <select
          className="cron-pill cron-pill--native"
          aria-label={TEXT.labelFrequency}
          value={period.frequency}
          onChange={e => patch({ frequency: e.target.value as PeriodFrequency })}
        >
          {FREQUENCY_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      <div className="cron-drawer__setting-row">
        <span className="cron-drawer__setting-label">{TEXT.labelTime}</span>
        <TimePicker hour={period.hour} minute={period.minute} onChange={(h, m) => patch({ hour: h, minute: m })} />
      </div>

      {/* 生效日期区间:定时任务的到期时间(如"到 2026-08-31 生效"),前端交互,后端暂不支持 */}
      <div className="cron-drawer__setting-row">
        <span className="cron-drawer__setting-label">{TEXT.labelDateRange}</span>
        <div className="cron-drawer__date-range">
          <input
            type="date"
            className="cron-pill"
            aria-label={TEXT.dateRangeStartPh}
            value={dateRange.start}
            onChange={e => setDateRange(prev => ({ ...prev, start: e.target.value }))}
          />
          <span className="cron-drawer__date-range-sep">{TEXT.dateRangeSep}</span>
          <input
            type="date"
            className="cron-pill"
            aria-label={TEXT.dateRangeEndPh}
            value={dateRange.end}
            onChange={e => setDateRange(prev => ({ ...prev, end: e.target.value }))}
          />
        </div>
      </div>

      <div className="cron-drawer__setting-row">
        <span className="cron-drawer__setting-label">{TEXT.labelTimezone}</span>
        <select className="cron-pill cron-pill--native" aria-label={TEXT.labelTimezone} value={timezone} onChange={e => onTimezoneChange(e.target.value)}>
          {TIMEZONE_OPTIONS.map(tz => (
            <option key={tz} value={tz}>
              {tz}
            </option>
          ))}
        </select>
      </div>

      {/* 频率专属控件 */}
      {period.frequency === 'weekly' ? (
        <div className="cron-sb__weekdays" role="group" aria-label={TEXT.groupWeekdays}>
          {WEEKDAYS.map(day => {
            const active = period.weekdays.includes(day);
            return (
              <button
                key={day}
                type="button"
                className={`cron-sb__weekday${active ? ' cron-sb__weekday--active' : ''}`}
                aria-pressed={active}
                onClick={() => toggleWeekday(day)}
              >
                {WEEKDAY_LABELS[day]}
              </button>
            );
          })}
        </div>
      ) : null}

      {period.frequency === 'monthly' ? (
        <div className="cron-sb__row">
          <label className="cron-sb__inline">
            <span>{TEXT.domLabel}</span>
            <input
              className="cron-sb__number"
              type="number"
              min={1}
              max={31}
              value={period.dayOfMonth}
              onChange={e => patch({ dayOfMonth: clampDayOfMonth(parseInt(e.target.value, 10)) })}
            />
          </label>
        </div>
      ) : null}

      {period.frequency === 'yearly' ? (
        <div className="cron-sb__row">
          <label className="cron-sb__inline">
            <span>{TEXT.monthLabel}</span>
            <input
              className="cron-sb__number"
              type="number"
              min={1}
              max={12}
              value={period.month}
              onChange={e => patch({ month: clampMonth(parseInt(e.target.value, 10)) })}
            />
          </label>
          <label className="cron-sb__inline">
            <span>{TEXT.dayLabel}</span>
            <input
              className="cron-sb__number"
              type="number"
              min={1}
              max={31}
              value={period.dayOfMonth}
              onChange={e => patch({ dayOfMonth: clampDayOfMonth(parseInt(e.target.value, 10)) })}
            />
          </label>
        </div>
      ) : null}
    </div>
  );
}
