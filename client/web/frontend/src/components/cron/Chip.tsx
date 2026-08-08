/**
 * Chip — 分类标签(基础标签)。设计稿:个人工作 / 财经 / 人力资源 …
 * bg=cron-tint,radius 4px,padding 2px 8px,12px/20px,前置可选图标。
 */
import { getCronIcon } from './cronIcons';

export interface ChipProps {
  label: string;
  /** 前置图标名(见 cronIcons);不传则纯文本 */
  iconName?: string;
}

export function Chip({ label, iconName }: ChipProps) {
  const Icon = iconName ? getCronIcon(iconName) : undefined;
  return (
    <span className="cron-chip">
      {Icon ? <Icon size={14} aria-hidden /> : null}
      <span>{label}</span>
    </span>
  );
}
