/**
 * TimePicker — 时间选择器(单触发 + 双列弹出面板)。
 *
 * 收起态:显示 HH:MM + chevron,与其它设置行下拉一致(设计稿 1:1)。
 * 展开态:弹出"时(00-23) | 分(00-59)"两列滚动列表,各自独立选择。
 * 点击外部自动关闭。
 */
import { useEffect, useRef, useState } from 'react';
import { clampHour, clampMinute } from '../../../utils/scheduleBuilder';

const HOUR_OPTIONS: readonly number[] = Array.from({ length: 24 }, (_, i) => i);
const MINUTE_OPTIONS: readonly number[] = Array.from({ length: 60 }, (_, i) => i);

const pad2 = (n: number) => String(n).padStart(2, '0');

export interface TimePickerProps {
  hour: number;
  minute: number;
  onChange: (hour: number, minute: number) => void;
}

export function TimePicker({ hour, minute, onChange }: TimePickerProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const hourListRef = useRef<HTMLDivElement>(null);
  const minuteListRef = useRef<HTMLDivElement>(null);

  // 点击外部关闭
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  // 展开时滚动到当前选中项
  useEffect(() => {
    if (!open) return;
    const itemH = 30; // 每项高度(padding 4*2 + line-height 22)
    const listH = 120; // 可视区高度
    const scroll = (selected: number) => Math.max(0, selected * itemH - (listH - itemH) / 2);
    if (hourListRef.current) hourListRef.current.scrollTop = scroll(hour);
    if (minuteListRef.current) minuteListRef.current.scrollTop = scroll(minute);
  }, [open, hour, minute]);

  const display = `${pad2(hour)}:${pad2(minute)}`;

  return (
    <div className="cron-time-picker" ref={containerRef}>
      <button type="button" className="cron-pill cron-pill--native" aria-label="时间" aria-expanded={open} onClick={() => setOpen(o => !o)}>
        {display}
      </button>
      {open ? (
        <div className="cron-time-picker__panel">
          <div className="cron-time-picker__col">
            <div className="cron-time-picker__col-label">时</div>
            <div className="cron-time-picker__list" ref={hourListRef}>
              {HOUR_OPTIONS.map(h => (
                <button
                  key={h}
                  type="button"
                  className={`cron-time-picker__item${h === hour ? ' cron-time-picker__item--active' : ''}`}
                  onClick={() => onChange(clampHour(h), minute)}
                >
                  {pad2(h)}
                </button>
              ))}
            </div>
          </div>
          <div className="cron-time-picker__divider" />
          <div className="cron-time-picker__col">
            <div className="cron-time-picker__col-label">分</div>
            <div className="cron-time-picker__list" ref={minuteListRef}>
              {MINUTE_OPTIONS.map(m => (
                <button
                  key={m}
                  type="button"
                  className={`cron-time-picker__item${m === minute ? ' cron-time-picker__item--active' : ''}`}
                  onClick={() => onChange(hour, clampMinute(m))}
                >
                  {pad2(m)}
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
