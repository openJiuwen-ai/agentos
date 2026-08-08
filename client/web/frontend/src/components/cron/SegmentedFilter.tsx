/**
 * SegmentedFilter — 按钮单选组(全部任务 / 运行中 / 已暂停)。
 * 设计稿:每个分段=白卡(radius 4px)+ 细阴影;选中=主色文本(#191919),未选=次色(#777)。
 * 通用受控组件,value/onChange 由父级驱动;文案经 options 透传,保持 i18n 无关。
 */
export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
}

export interface SegmentedFilterProps<T extends string> {
  options: readonly SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
}

export function SegmentedFilter<T extends string>({ options, value, onChange }: SegmentedFilterProps<T>) {
  return (
    <div className="cron-segmented" role="tablist">
      {options.map(opt => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            role="tab"
            aria-selected={active}
            className={`cron-segmented__item${active ? ' cron-segmented__item--active' : ''}`}
            onClick={() => onChange(opt.value)}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
