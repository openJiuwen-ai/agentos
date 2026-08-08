/**
 * CronCard — 单个任务卡(原子)。1:1 对照设计稿"定时任务 - 首页"card(457px)。
 *
 * 结构(DSL):卡片(无 border / radius24 / 双层阴影 / padding 20·24)
 *   → 内层 409px(gap 20):顶部组(gap 12)[标题行(name | 开关) + 可选分类标签]
 *                        + 可选描述(2 行截断)
 *                        + 底部行(ScheduleLabel 左 | NextRunLabel 右)
 *
 * 静态态与设计稿一致:右上角只有开关。"更多"省略号菜单(编辑/立即执行/删除)是功能入口,
 * 仅在卡片 hover 或菜单打开时淡入(opacity 0→1),不影响静态截图与设计稿 1:1。
 *
 * 开关:CSS 还原,ON=#0A59F7(设计稿 30_41486.png 采样),36×20 + 白钮。
 * 分类标签:数据驱动,无 category 时不渲染(后端 CronJob 无此列,决策 ⑥)。
 * description / nextRunAt 由父级异步取回注入(SidebarCronJob 列表无 description)。
 * 文案取设计稿原文中文(不用 i18n,避免跟随浏览器语言变英文,与原版 1:1)。
 */
import { useEffect, useRef, useState } from 'react';
import type { ViewMode } from '../../types';
import { ScheduleLabel } from './ScheduleLabel';
import { NextRunLabel } from './NextRunLabel';
import { CronSvgIcon, type CronSvgIconName } from './cronSvgIcons';
import { getCronIcon } from './cronIcons';

export interface CronCardProps {
  id: string;
  name: string;
  /** 分类标签(可选)——后端 list 无此字段;有则渲染 图标+文字 标签 */
  category?: string;
  /** 分类标签图标,默认 folder(设计稿"个人工作");"健康"等用 redcross */
  categoryIconName?: CronSvgIconName;
  /** 描述(可选)——父级 getJob 取回;空则不渲染 */
  description?: string;
  enabled: boolean;
  expired: boolean;
  /** 5 段标准 cron,ScheduleLabel 据此派生自然语言调度 */
  cronExpr: string;
  /** 下次执行(epoch 秒/毫秒/ISO);父级 previewJob 取回;空/null 则不渲染 */
  nextRunAt?: number | string | null;
  viewMode: ViewMode;
  onToggle: (id: string) => void;
  onRunNow: (id: string) => void;
  onDelete: (id: string) => void;
  /** Phase 3:编辑(开抽屉) */
  onEdit: (id: string) => void;
  /** Phase 3:创建完成态高亮(2s 闪;设计无,UX 增强) */
  flash?: boolean;
}

export function CronCard({
  id,
  name,
  category,
  categoryIconName = 'folder',
  description,
  enabled,
  expired,
  cronExpr,
  nextRunAt,
  viewMode,
  onToggle,
  onRunNow,
  onDelete,
  onEdit,
  flash,
}: CronCardProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const EllipsisIcon = CronSvgIcon.ellipsis;
  const TagIcon = CronSvgIcon[categoryIconName] ?? CronSvgIcon.folder;
  const EditIcon = getCronIcon('edit');
  const PlayIcon = getCronIcon('play');
  const TrashIcon = getCronIcon('trash');

  const toggleDisabled = expired;
  // 仅过期卡片整卡淡化;暂停态由开关 OFF 表达,卡片保持正常(设计稿只画了启用态)。
  const dimmed = expired;

  useEffect(() => {
    if (!menuOpen) return undefined;
    const onMouseDown = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, [menuOpen]);

  return (
    <div
      className={[
        'cron-card',
        viewMode === 'grid' ? 'cron-card--grid' : '',
        dimmed ? 'cron-card--disabled' : '',
        flash ? 'cron-card--flash' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <div className="cron-card__inner">
        <div className="cron-card__top">
          <div className="cron-card__title-row">
            <div className="cron-card__name" title={name}>{name}</div>
            <div className="cron-card__actions">
              <div className={`cron-card-menu${menuOpen ? ' cron-card-menu--open' : ''}`} ref={menuRef}>
                <button
                  type="button"
                  className="cron-card-menu__btn"
                  aria-label="更多操作"
                  aria-haspopup="menu"
                  aria-expanded={menuOpen}
                  onClick={() => setMenuOpen(prev => !prev)}
                >
                  <EllipsisIcon className="cron-card-menu__icon" aria-hidden />
                </button>
                {menuOpen ? (
                  <div className="cron-card-menu__panel" role="menu">
                    <button
                      type="button"
                      role="menuitem"
                      className="cron-card-menu__item"
                      onClick={() => {
                        setMenuOpen(false);
                        onEdit(id);
                      }}
                    >
                      {EditIcon ? <EditIcon size={14} aria-hidden /> : null}
                      <span>编辑</span>
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      className="cron-card-menu__item"
                      onClick={() => {
                        setMenuOpen(false);
                        onRunNow(id);
                      }}
                    >
                      {PlayIcon ? <PlayIcon size={14} aria-hidden /> : null}
                      <span>立即执行</span>
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      className="cron-card-menu__item cron-card-menu__item--danger"
                      onClick={() => {
                        setMenuOpen(false);
                        onDelete(id);
                      }}
                    >
                      {TrashIcon ? <TrashIcon size={14} aria-hidden /> : null}
                      <span>删除</span>
                    </button>
                  </div>
                ) : null}
              </div>
              <button
                type="button"
                className={`cron-toggle${enabled ? ' cron-toggle--on' : ''}`}
                role="switch"
                aria-checked={enabled}
                aria-label="启用/停用"
                disabled={toggleDisabled}
                onClick={() => onToggle(id)}
              >
                <span className="cron-toggle__knob" />
              </button>
            </div>
          </div>
          {category ? (
            <span className="cron-card__tag">
              <TagIcon className="cron-card__tag-icon" aria-hidden />
              <span className="cron-card__tag-text">{category}</span>
            </span>
          ) : null}
        </div>
        {description ? <p className="cron-card__desc">{description}</p> : null}
        <div className="cron-card__foot">
          <ScheduleLabel cronExpr={cronExpr} />
          {nextRunAt !== undefined && nextRunAt !== null && nextRunAt !== '' ? (
            <NextRunLabel value={nextRunAt} />
          ) : null}
        </div>
      </div>
    </div>
  );
}
