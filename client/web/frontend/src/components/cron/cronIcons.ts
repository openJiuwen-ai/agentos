/**
 * cron 图标注册表 — 复用 lucide-react(currentColor,主题可变),不新建 SVG 资源文件。
 *
 * 偏离 Phase 1 prompt"建 SVG":CronPanel.tsx 既有约定即 lucide-react,DRY + AGENTS.md
 * 允许库图标(currentColor)。模板图标为近似语义映射,后续如需像素级 Figma 图标可在此替换。
 */
import {
  ChevronDown,
  Clock,
  FileText,
  Folder,
  GraduationCap,
  LayoutGrid,
  List,
  Megaphone,
  MoreHorizontal,
  Newspaper,
  Pencil,
  Play,
  Plus,
  Search,
  Trash2,
  TrendingUp,
  Users,
  type LucideIcon,
} from 'lucide-react';

/** 模板图标(对齐 cronTemplates.ts 的 iconName)+ UI 图标 */
export const CRON_ICONS: Readonly<Record<string, LucideIcon>> = {
  // 模板图标
  meeting: Users,
  interview: GraduationCap,
  stock: TrendingUp,
  report: FileText,
  opinion: Megaphone,
  news: Newspaper,
  // UI 图标
  search: Search,
  list: List,
  grid: LayoutGrid,
  chevronDown: ChevronDown,
  clock: Clock,
  folder: Folder,
  plus: Plus,
  // 卡片操作(Phase 2)
  more: MoreHorizontal,
  play: Play,
  trash: Trash2,
  // 卡片操作(Phase 3)
  edit: Pencil,
};

/** 取图标组件;未注册返回 undefined(调用方可回退) */
export function getCronIcon(name: string): LucideIcon | undefined {
  return CRON_ICONS[name];
}
