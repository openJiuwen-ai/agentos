/**
 * 定时任务(cron)类型定义 — Phase 0 契约层
 *
 * CronJobDTO 对齐后端 CronJob.to_dict()
 * (jiuwenswarm/jiuwenswarm/gateway/cron/models.py)。精简回退轮:只保留基本字段
 * (name/description/cron_expr/timezone/targets/enabled/wake_offset_seconds 等),
 * 撤销 model/permission/media_items/files/skills 等丰富字段(后端已回退 HEAD)。
 * 其余 UI 类型供 Phase 2/3 渲染层使用。
 */

/** 后端 CronJob.to_dict() 线上协议:always-present 字段 + falsy 时省略的可选字段。 */
export interface CronJobDTO {
  id: string;
  name: string;
  enabled: boolean;
  expired: boolean;
  cron_expr: string;
  timezone: string;
  wake_offset_seconds: number;
  description: string;
  /** 推送频道 ID(后端 normalize 为单个 CronTargetChannel;空串→'web') */
  targets: string;
  /** epoch 秒,后端 float|null */
  created_at: number | null;
  updated_at: number | null;
  /** 以下字段后端 to_dict() 在 falsy 时省略,前端按可选处理 */
  session_id?: string;
  /** 'group' | '2pp' 等(后端为自由字符串,不枚举) */
  chat_type?: string;
  /** 'plan' | 'agent',默认 'agent' */
  mode?: string;
  delete_after_run?: boolean;
  /** 前端侧注入:web channel list handler 装饰;后端 to_dict() 不含 */
  project_id?: string;
}

/** 调度构建器内部形态(后端只持久化 cron_expr 字符串;此类型仅 UI 构建过程用) */
export type CronScheduleKind = 'cron' | 'every' | 'at';

export interface CronSchedule {
  kind: CronScheduleKind;
  /** kind='cron' 时:5 段标准 cron(分 时 日 月 周) */
  expr?: string;
  /** kind='cron' 时:时区 */
  tz?: string;
  /** kind='at' 时:ISO8601 时刻 */
  at?: string;
  /** kind='every' 时:间隔毫秒 */
  everyMs?: number;
}

/** 列表筛选(设计稿"全部/运行中/已暂停") */
export type FilterKind = 'all' | 'running' | 'paused';

/** 视图模式(设计稿视图切换) */
export type ViewMode = 'list' | 'grid';

/** cron.job.preview 返回的单条下次执行 */
export interface CronPreviewItem {
  /** 唤醒时刻 ISO(wake_offset 应用前) */
  wake_at: string;
  /** 推送时刻 ISO(wake_offset 应用后) */
  push_at: string;
}

/** 编辑表单输入(normalizeJobForEdit 的输出 / 编辑表单 state 形态) */
export interface CronJobEditInput {
  id: string;
  name: string;
  enabled: boolean;
  cron_expr: string;
  timezone: string;
  wake_offset_seconds: number;
  description: string;
  targets: string;
  created_at: number | null;
  updated_at: number | null;
}

/** cron.job.update 的 patch(不含不可改字段) */
export type CronJobPatch = Partial<Omit<CronJobEditInput, 'id' | 'created_at' | 'updated_at'>>;

/** 卡片渲染用 UI 任务(Phase 2 消费;Phase 0 仅定义) */
export interface CronTaskUI {
  id: string;
  name: string;
  /** 分类标签(个人工作/财经/…)— 设计稿有,后端无,UI 派生 */
  category: string;
  enabled: boolean;
  expired: boolean;
  description: string;
  cronExpr: string;
  timezone: string;
  targets: string;
  /** 自然语言调度"每周五 17:00"(UI 派生自 cronExpr) */
  scheduleLabel: string;
  createdAt: number | null;
  updatedAt: number | null;
}

/** 任务模板(Phase 3 静态常量) */
export interface CronTemplateUI {
  id: string;
  name: string;
  category: string;
  /** 提示词(Phase 3 填充) */
  prompt: string;
  /** 自然语言调度 */
  scheduleLabel: string;
  /** 5 段标准 cron(后端 normalize 为 7 段 Quartz) */
  cronExpr: string;
  /** 图标标识(lucide 兜底;iconUrl 优先) */
  iconName: string;
  /** 彩色插画图标 URL(设计稿模板卡插图 PNG;优先于 iconName) */
  iconUrl?: string;
}
