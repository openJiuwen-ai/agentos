/**
 * 任务模板静态常量(Phase 3 填充提示词文案)— 决策#2:纯前端常量,无后端。
 *
 * 6 模板的名称 / 顺序 / 调度 / cron / prompt 文案均取自设计稿
 * "定时任务 - 空白首页"/index.html 第 13 行模板区段(设计稿 = 唯一文案真源,1:1)。
 * 调度统一用 5 段标准 cron(分 时 日 月 周,周 1=周一..7=周日),后端 normalize 为 7 段 Quartz。
 * 模板卡插图 iconUrl 取自设计稿「定时任务图标」清洗后 SVG(保留原始几何 + opacity),
 * 优先于 iconName(lucide 兜底)。
 *
 * ⚠ 设计稿原文保留两处疑似笔误("你所在点行业" / "在全网点最新动态"),按 1:1 硬约束照抄,
 *    待用户裁定是否订正(见研究报告 Phase 3 偏离表)。
 * ⚠ 工作周报:空白首页模板描述为"每周五下午6点"→ cron `0 18 * * 5`(18:00);
 *    首页示例卡"工作周报"为 17:00,二者为不同示例,以各自描述为准。
 * ⚠ 每日股市简报:设计稿描述"每个开盘日早上8点半"→ 工作日 08:30(`30 8 * * 1-5`)。
 */
import type { CronTemplateUI } from '../types/cron';
// 6 模板插图(设计稿「定时任务图标」清洗后 SVG,保留设计稿原始几何 + opacity)
import industryNewsIcon from '../assets/cron/templates/industry-news.svg';
import opinionTrackingIcon from '../assets/cron/templates/opinion-tracking.svg';
import weeklyReportIcon from '../assets/cron/templates/weekly-report.svg';
import stockBriefingIcon from '../assets/cron/templates/stock-briefing.svg';
import interviewPrepIcon from '../assets/cron/templates/interview-prep.svg';
import meetingNotesIcon from '../assets/cron/templates/meeting-notes.svg';

export const CRON_TEMPLATES: readonly CronTemplateUI[] = [
  {
    id: 'industry-news',
    name: '每日行业资讯',
    category: '资讯研究',
    prompt: '每天早上8点，给我推送当天【你所在点行业，例如：人工客服/金融/新能源】的最新行业资讯动态，整理成结构化文档发出',
    scheduleLabel: '每天 08:00',
    cronExpr: '0 8 * * *',
    iconName: 'news',
    iconUrl: industryNewsIcon,
  },
  {
    id: 'opinion-tracking',
    name: '市场舆情追踪',
    category: '市场品牌',
    prompt: '每天中午12点，帮我搜索并汇总竞争对手【某公司或某某产品】过去24小时在全网点最新动态和舆情报道',
    scheduleLabel: '每天 12:00',
    cronExpr: '0 12 * * *',
    iconName: 'opinion',
    iconUrl: opinionTrackingIcon,
  },
  {
    id: 'weekly-report',
    name: '工作周报',
    category: '个人工作',
    prompt: '每周五下午6点，帮我根据本周聊天、文档、表格、生成我的周报，任务进度，下周事项工作安排，并且以文档形式发出',
    scheduleLabel: '每周五 18:00',
    cronExpr: '0 18 * * 5',
    iconName: 'report',
    iconUrl: weeklyReportIcon,
  },
  {
    id: 'stock-briefing',
    name: '每日股市简报',
    category: '财经',
    prompt: '每个开盘日早上8点半，汇总今日重点市场动态、自选股表现和重要财经新闻，分析主要涨跌原因，并整理明日值得关注的事件。',
    scheduleLabel: '工作日 08:30',
    cronExpr: '30 8 * * 1-5',
    iconName: 'stock',
    iconUrl: stockBriefingIcon,
  },
  {
    id: 'interview-prep',
    name: '面试准备提醒',
    category: '人力资源',
    prompt: '工作日每6小时，根据我近期的面试安排和目标岗位，整理公司背景、岗位重点、常见面试问题和需要准备的材料，生成面试准备清单。',
    scheduleLabel: '工作日每6小时',
    cronExpr: '0 */6 * * 1-5',
    iconName: 'interview',
    iconUrl: interviewPrepIcon,
  },
  {
    id: 'meeting-notes',
    name: '会议纪要整理',
    category: '办公',
    prompt: '每个工作日下午6点半，汇总当天会议内容，提炼关键结论、决策事项、负责人和后续待办，并生成结构化会议纪要。',
    scheduleLabel: '工作日 18:30',
    cronExpr: '30 18 * * 1-5',
    iconName: 'meeting',
    iconUrl: meetingNotesIcon,
  },
];
