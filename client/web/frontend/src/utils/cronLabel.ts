/**
 * cron 表达式 → 中文自然语言调度标签 + 下次执行时间格式化 — 纯函数,便于单测。
 *
 * 设计稿"每周五 17:00""工作日 15:30""每天 09:00"等取自 ScheduleLabel / NextRunLabel。
 * 5 段标准 cron(分 时 日 月 周,周 1=周一..7=周日),与 utils/cronTemplates.ts 对齐;
 * 7 段 Quartz(秒 分 时 日 月 周 年)取字段 [1..5] 等价解析,? 视为通配。
 * 仅覆盖常见模式;无法识别时原样返回 cron 串,不抛错(调用方自行决定是否回退展示)。
 */

const WEEKDAY_CN: Readonly<Record<string, string>> = {
  '1': '一',
  '2': '二',
  '3': '三',
  '4': '四',
  '5': '五',
  '6': '六',
  '7': '日',
};

interface CronFields {
  min: string;
  hr: string;
  dom: string;
  mon: string;
  dow: string;
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

function isWildcard(field: string): boolean {
  return field === '*' || field === '?';
}

function parseFields(expr: string): CronFields | null {
  const parts = String(expr ?? '')
    .trim()
    .split(/\s+/)
    .filter(p => p.length > 0);
  if (parts.length === 5) {
    return { min: parts[0], hr: parts[1], dom: parts[2], mon: parts[3], dow: parts[4] };
  }
  if (parts.length === 7) {
    // Quartz:秒 分 时 日 月 周 年 → 取 [1..5]
    return { min: parts[1], hr: parts[2], dom: parts[3], mon: parts[4], dow: parts[5] };
  }
  return null;
}

function simpleInt(field: string): number | null {
  if (!/^\d+$/.test(field)) return null;
  const n = parseInt(field, 10);
  return Number.isInteger(n) ? n : null;
}

function timeLabel(min: string, hr: string): string | null {
  const m = simpleInt(min);
  const h = simpleInt(hr);
  if (m === null || h === null) return null;
  return `${pad2(h)}:${pad2(m)}`;
}

function dowToCn(dow: string): string | null {
  if (dow === '1-5') return '工作日';
  if (/^\d+(,\d+)*$/.test(dow)) {
    const nums = dow.split(',');
    if (nums.every(n => WEEKDAY_CN[n] !== undefined)) {
      return `每周${nums.map(n => WEEKDAY_CN[n]).join('')}`;
    }
  }
  return null;
}

/**
 * 把 cron 表达式转成"每周五 17:00"式中文调度标签。
 * 空串→空串;段数非法或无法识别→原样返回。
 */
export function cronToScheduleLabel(expr: string): string {
  const raw = String(expr ?? '').trim();
  if (raw === '') return '';
  const f = parseFields(raw);
  if (!f) return raw;

  const time = timeLabel(f.min, f.hr);

  // 周维度
  if (!isWildcard(f.dow)) {
    const cn = dowToCn(f.dow);
    if (cn && time) return `${cn} ${time}`;
    return raw;
  }

  // 月维度(周通配、日指定)
  if (!isWildcard(f.dom) && isWildcard(f.mon)) {
    const dom = simpleInt(f.dom);
    if (dom !== null && time) return `每月 ${dom} 日 ${time}`;
    return raw;
  }

  const allDayFields = isWildcard(f.dom) && isWildcard(f.mon) && isWildcard(f.dow);

  // 间隔:分钟步长
  if (/^\*\/\d+$/.test(f.min) && isWildcard(f.hr) && allDayFields) {
    return `每 ${f.min.slice(2)} 分钟`;
  }
  // 间隔:小时步长
  if (simpleInt(f.min) === 0 && /^\*\/\d+$/.test(f.hr) && allDayFields) {
    return `每 ${f.hr.slice(2)} 小时`;
  }

  // 每天
  if (allDayFields && time) return `每天 ${time}`;

  return raw;
}

/**
 * 把时间戳/ISO 串格式化成设计稿 NextRunLabel 用的"YYYY/MM/DD HH:mm"(本地时区)。
 * null / 非法值 → 空串。秒级时间戳(<1e11)自动按秒解释。
 */
export function formatCronDateTime(value: number | string | null): string {
  if (value == null) return '';
  const ms = typeof value === 'number' ? (value < 1e11 ? value * 1000 : value) : Date.parse(value);
  if (!Number.isFinite(ms)) return '';
  const d = new Date(ms);
  return `${d.getFullYear()}/${pad2(d.getMonth() + 1)}/${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}
