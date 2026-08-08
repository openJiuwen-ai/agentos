/**
 * ScheduleLabel — 自然语言调度标签(每周五 17:00 / 工作日 15:30 …)。
 * 设计稿:前置时钟图标 + 文本,均 rgba(0,0,0,0.3)/14px/400/19px。文本由 cronExpr 经
 * cronToScheduleLabel 派生;label 显式传入则覆盖(供模板直出 scheduleLabel)。
 * 时钟图标用设计系统 CronSvgIcon.clock(currentColor),随文本一起取 faint 色。
 */
import { cronToScheduleLabel } from '../../utils/cronLabel';
import { CronSvgIcon } from './cronSvgIcons';

export interface ScheduleLabelProps {
  /** 5 段标准 cron(或 7 段 Quartz) */
  cronExpr: string;
  /** 覆盖派生文本 */
  label?: string;
}

export function ScheduleLabel({ cronExpr, label }: ScheduleLabelProps) {
  const Icon = CronSvgIcon.clock;
  const text = label ?? cronToScheduleLabel(cronExpr);
  if (!text) return null;
  return (
    <span className="cron-schedule-label">
      <Icon className="cron-schedule-label__icon" aria-hidden />
      <span>{text}</span>
    </span>
  );
}
