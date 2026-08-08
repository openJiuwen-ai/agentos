/**
 * CronTemplateCard — 单个模板卡。1:1 对照设计稿"定时任务 - 空白首页"模板区段。
 *
 * 结构(DSL):与任务卡同壳(457 / 白底 / radius24 / 双层阴影 / padding20·24 / gap20,纵向)
 *   → 彩色插图(≈30)+ 名称(20/500/27 #000)+ prompt 描述(14/500/24 rgba(0,0,0,0.5) 截2行)。
 * 插图优先用 template.iconUrl(设计稿 SVG);无则回退 iconName(lucide currentColor)。
 * 设计稿无独立"使用"按钮,整卡可点击 → onUse(开抽屉 template 模式预填)。
 */
import type { CronTemplateUI } from '../../types';
import { getCronIcon } from './cronIcons';

export interface CronTemplateCardProps {
  template: CronTemplateUI;
  onUse: (template: CronTemplateUI) => void;
}

export function CronTemplateCard({ template, onUse }: CronTemplateCardProps) {
  const FallbackIcon = getCronIcon(template.iconName);
  return (
    <button type="button" className="cron-template-card" onClick={() => onUse(template)}>
      {template.iconUrl ? (
        <img className="cron-template-card__icon" src={template.iconUrl} alt="" draggable={false} />
      ) : FallbackIcon ? (
        <span className="cron-template-card__icon cron-template-card__icon--fallback">
          <FallbackIcon size={30} aria-hidden />
        </span>
      ) : null}
      <span className="cron-template-card__name">{template.name}</span>
      <span className="cron-template-card__desc">{template.prompt}</span>
    </button>
  );
}
