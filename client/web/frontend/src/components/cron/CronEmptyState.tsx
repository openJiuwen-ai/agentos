/**
 * CronEmptyState — 任务列表"筛选/搜索无命中"次级空态。
 *
 * 设计稿空白首页在"无任何任务"时直接渲染模板区段(TaskTemplateSection,从这里开始),
 * 故本组件仅用于"有任务但当前 filter/search 无命中"的次级空态。
 * 文案取设计稿语境中文(不用 i18n,避免跟随浏览器语言)。
 */
import { getCronIcon } from './cronIcons';

const NO_RESULTS_TEXT = '未找到相关任务，可换个关键词再试。';

export function CronEmptyState() {
  const Icon = getCronIcon('folder');
  return (
    <div className="cron-empty-state">
      {Icon ? <Icon size={36} aria-hidden /> : null}
      <span className="cron-empty-state__text">{NO_RESULTS_TEXT}</span>
    </div>
  );
}
