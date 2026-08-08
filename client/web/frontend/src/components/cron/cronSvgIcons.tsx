/**
 * cron 设计系统图标 — 1:1 取自高保真设计稿的 HarmonyOS 公共图标(ic_public_*),
 * 经 vite-plugin-svgr 内联为 React 组件,故支持 currentColor —— 颜色由 cronTokens.css
 * 令牌控制,几何完全对齐设计稿。替换 cronIcons.ts 里的 lucide 近似图标,根治"图标不一致"。
 *
 * 清洗说明:源 SVG(设计数据/图标/)是 Figma 导出,带容器 rect / mask / 双层 clipPath 噪声;
 * 这里只保留每个图标的真实图元(path/circle),去噪后几何与设计稿逐点一致。
 *
 * 未在此导出的图标(开关 ON·OFF)在设计图标库里无干净 SVG,且开关为两态交互控件,
 * 故用 CSS 还原(见 cronPage.css .cron-toggle,ON=#0A59F7 取自设计稿 30_41486.png 采样)。
 * clock 取自设计稿 ic_public_clock 几何;folder / redcross 几何简单,手绘 currentColor SVG。
 * view-grid / view-list 取自设计稿「定时任务图标」(加-1 / 加),保留 rgb(0,0,0) + opacity。
 */
import type { ComponentType, SVGProps } from 'react';
import Ellipsis from '../../assets/cron/icons/ellipsis.svg?react';
import Plus from '../../assets/cron/icons/plus.svg?react';
import ChevronDown from '../../assets/cron/icons/chevron-down.svg?react';
import Search from '../../assets/cron/icons/search.svg?react';
import Folder from '../../assets/cron/icons/folder.svg?react';
import Close from '../../assets/cron/icons/close.svg?react';
import ViewGrid from '../../assets/cron/icons/view-grid.svg?react';
import ViewList from '../../assets/cron/icons/view-list.svg?react';
import Clock from '../../assets/cron/icons/clock.svg?react';
import Redcross from '../../assets/cron/icons/redcross.svg?react';

/** 设计系统 SVG 图标(内联,currentColor)。所有图标均接受标准 SVGProps(width/color 等)。 */
export const CronSvgIcon = {
  ellipsis: Ellipsis,
  plus: Plus,
  chevronDown: ChevronDown,
  search: Search,
  folder: Folder,
  close: Close,
  viewGrid: ViewGrid,
  viewList: ViewList,
  clock: Clock,
  redcross: Redcross,
} as const;

export type CronSvgIconName = keyof typeof CronSvgIcon;

export type CronSvgIconComponent = ComponentType<SVGProps<SVGSVGElement>>;

/** 取图标组件;未注册返回 undefined(调用方可回退到 lucide)。 */
export function getCronSvgIcon(name: CronSvgIconName): CronSvgIconComponent {
  return CronSvgIcon[name];
}
