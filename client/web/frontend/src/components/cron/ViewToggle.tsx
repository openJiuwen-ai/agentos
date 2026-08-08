/**
 * ViewToggle — 视图切换(网格 / 列表)。
 * 1:1 设计稿:灰底槽(radius 8,padding 2)+ 两图标按钮;选中=白底(radius 6)。
 * 设计稿顺序:grid(左,默认选中)+ list(右)。图标用设计系统内联 SVG(cronSvgIcons)。
 */
import type { ViewMode } from '../../types';
import { CronSvgIcon } from './cronSvgIcons';

export interface ViewToggleProps {
  value: ViewMode;
  onChange: (value: ViewMode) => void;
}

const MODES: readonly { mode: ViewMode; icon: 'viewGrid' | 'viewList'; label: string }[] = [
  { mode: 'grid', icon: 'viewGrid', label: '网格视图' },
  { mode: 'list', icon: 'viewList', label: '列表视图' },
];

export function ViewToggle({ value, onChange }: ViewToggleProps) {
  return (
    <div className="cron-view-toggle" role="group">
      {MODES.map(({ mode, icon, label }) => {
        const Icon = CronSvgIcon[icon];
        const active = mode === value;
        return (
          <button
            key={mode}
            type="button"
            aria-label={label}
            aria-pressed={active}
            className={`cron-view-toggle__btn${active ? ' cron-view-toggle__btn--active' : ''}`}
            onClick={() => onChange(mode)}
          >
            <Icon className="cron-view-toggle__icon" aria-hidden />
          </button>
        );
      })}
    </div>
  );
}
