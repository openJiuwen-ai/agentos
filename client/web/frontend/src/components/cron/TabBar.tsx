/**
 * TabBar — 基础页签组(任务列表 / 执行历史 / 任务模板)。
 * 1:1 设计稿:18px/24px;选中=#000(font-weight 700);未选=rgba(0,0,0,0.4)(400)。无下划线
 * (旧实现有 2px 下划线,设计稿无 —— 已移除)。通用受控组件;tabs 文案透传。
 */
export interface TabOption<T extends string> {
  value: T;
  label: string;
}

export interface TabBarProps<T extends string> {
  tabs: readonly TabOption<T>[];
  value: T;
  onChange: (value: T) => void;
}

export function TabBar<T extends string>({ tabs, value, onChange }: TabBarProps<T>) {
  return (
    <div className="cron-tab-bar" role="tablist">
      {tabs.map(tab => {
        const active = tab.value === value;
        return (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={active}
            className={`cron-tab-bar__tab${active ? ' cron-tab-bar__tab--active' : ''}`}
            onClick={() => onChange(tab.value)}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
