/**
 * CreateDropdown — 创建下拉(手动创建 / 通过聊天创建)。
 *
 * 触发器三变体(1:1 设计稿):
 *  - solid:页头黑色"创建"主按钮(bg #000 胶囊 radius 24 + 白色 chevron-down 后缀,无 plus)。
 *  - outline:空态"创建定时任务"轮廓按钮(白底 + plus 前缀;精确尺寸在空态 hero 原子微调)。
 *  - default:白卡按钮 + plus 前缀(通用,当前 4 屏未直接使用)。
 *
 * 图标用设计系统内联 SVG(cronSvgIcons,currentColor),替换原 lucide 近似图标。
 * 面板=白卡 + 阴影,选项 hover=cron-tint。自管 open 态,外部点击关闭。
 */
import { useEffect, useRef, useState } from 'react';
import { CronSvgIcon, type CronSvgIconName } from './cronSvgIcons';

export interface CreateDropdownItem {
  key: string;
  label: string;
  iconName?: CronSvgIconName;
}

export interface CreateDropdownProps {
  triggerLabel: string;
  items: readonly CreateDropdownItem[];
  onSelect: (key: string) => void;
  /** default/outline 触发器前置图标名,默认 plus(solid 不用) */
  triggerIconName?: CronSvgIconName;
  /** 触发器样式:default=白卡按钮;solid=黑色主按钮(页头 CTA);outline=白底轮廓(空态) */
  variant?: 'default' | 'solid' | 'outline';
}

export function CreateDropdown({ triggerLabel, items, onSelect, triggerIconName = 'plus', variant = 'default' }: CreateDropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const isSolid = variant === 'solid';
  const variantCls = isSolid ? ' cron-create-dropdown__trigger--solid' : variant === 'outline' ? ' cron-create-dropdown__trigger--outline' : '';
  const triggerCls = `cron-create-dropdown__trigger${variantCls}`;
  // solid = 「创建」+ chevron 后缀;default/outline = plus 前缀 + 标签。
  const PrefixIcon = isSolid ? null : (CronSvgIcon[triggerIconName] ?? CronSvgIcon.plus);
  const SuffixIcon = isSolid ? CronSvgIcon.chevronDown : null;

  useEffect(() => {
    if (!open) return undefined;
    const onMouseDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, [open]);

  return (
    <div className="cron-create-dropdown" ref={ref}>
      <button type="button" className={triggerCls} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(prev => !prev)}>
        {PrefixIcon ? <PrefixIcon className="cron-create-dropdown__icon" aria-hidden /> : null}
        <span>{triggerLabel}</span>
        {SuffixIcon ? <SuffixIcon className="cron-create-dropdown__icon cron-create-dropdown__icon--chevron" aria-hidden /> : null}
      </button>
      {open ? (
        <div className="cron-create-dropdown__panel" role="menu">
          {items.map(item => {
            const Icon = item.iconName ? CronSvgIcon[item.iconName] : undefined;
            return (
              <button
                key={item.key}
                type="button"
                role="menuitem"
                className="cron-create-dropdown__item"
                onClick={() => {
                  onSelect(item.key);
                  setOpen(false);
                }}
              >
                {Icon ? <Icon className="cron-create-dropdown__icon" aria-hidden /> : null}
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
