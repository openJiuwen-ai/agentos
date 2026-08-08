/**
 * TaskTemplateSection — 任务模板区段。对照设计稿"定时任务 - 空白首页"模板区。
 *
 * 标题"定时任务模板"+ "查看更多"链接(space-between)+ CronTemplateCard 网格。
 * 数据源 store.templates(6 项静态常量,Phase 0 已就位)。
 * 模板"使用"为占位回调 onUse(Phase 3 预填创建表单);"查看更多"→ onMore(父级切到模板 tab)。
 *
 * 文案严格取设计稿原文。刻意不用 i18n:其现存值("任务模板"/"更多")与设计稿
 * ("定时任务模板"/"查看更多")不一致,且 i18n 会跟随浏览器语言变英文 —— 与原版 1:1 要求冲突。
 */
import type { CronTemplateUI } from '../../types';
import { CronTemplateCard } from './CronTemplateCard';

export interface TaskTemplateSectionProps {
  templates: readonly CronTemplateUI[];
  onUse: (template: CronTemplateUI) => void;
  onMore?: () => void;
}

export function TaskTemplateSection({ templates, onUse, onMore }: TaskTemplateSectionProps) {
  return (
    <section className="cron-template-section">
      <div className="cron-template-section__head">
        <span className="cron-template-section__title">定时任务模板</span>
        <button type="button" className="cron-template-section__more" onClick={onMore}>
          查看更多
        </button>
      </div>
      <div className="cron-template-section__grid">
        {templates.map(tpl => (
          <CronTemplateCard key={tpl.id} template={tpl} onUse={onUse} />
        ))}
      </div>
    </section>
  );
}
