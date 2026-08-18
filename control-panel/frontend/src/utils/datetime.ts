/**
 * 将服务端返回的 ISO 时间串（UTC）转为浏览器本地时区，格式 YYYY-MM-DD HH:mm:ss。
 * 空值或非法日期返回 emptyText。
 */
export function formatDateTime(value: string | null | undefined, emptyText = '—'): string {
  if (!value) return emptyText;
  const d = new Date(value);
  if (isNaN(d.getTime())) return emptyText;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
