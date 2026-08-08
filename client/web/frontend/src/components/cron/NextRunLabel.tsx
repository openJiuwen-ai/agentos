/**
 * NextRunLabel — 下次执行时间(下次执行  2026/07/24 17:00)。
 * 设计稿:14px/22px,#777,前缀与日期间两空格,日期格式 YYYY/MM/DD HH:mm(本地时区)。
 * value 非法/空 → 不渲染。
 */
import { formatCronDateTime } from '../../utils/cronLabel';

export interface NextRunLabelProps {
  /** 时间戳(ms 或 s)/ ISO 串;null → 不渲染 */
  value: number | string | null;
  /** 前缀,默认"下次执行"(Phase 2 父级可注入 i18n) */
  prefix?: string;
}

export function NextRunLabel({ value, prefix = '下次执行' }: NextRunLabelProps) {
  const formatted = formatCronDateTime(value);
  if (!formatted) return null;
  return (
    <span className="cron-next-run-label">
      {prefix}&nbsp;&nbsp;{formatted}
    </span>
  );
}
