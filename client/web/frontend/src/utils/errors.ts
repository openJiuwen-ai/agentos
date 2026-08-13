/**
 * 错误消息人性化
 *
 * 后端/模型返回的错误往往是面向排障的原始信息，例如：
 *   [181001] model call failed, reason: openAI API async stream error:
 *   AuthenticationError: Error code: 401 - {'error': {'message': 'Invalid API-key provided...'}}
 *
 * 直接展示给用户既不美观也不易读。这里将常见错误模式映射为友好的中文文案，
 * 原始信息保留在 detail 中，UI 默认折叠、可展开查看（排障用）。
 */

export interface HumanizedError {
  /** 面向用户的友好标题 */
  title: string;
  /** 原始错误信息（UI 默认折叠） */
  detail?: string;
}

/** 兜底文案 */
export const FALLBACK_ERROR_TITLE = '服务暂时不可用，请稍后重试';

function matchAny(message: string, patterns: RegExp[]): boolean {
  return patterns.some((re) => re.test(message));
}

/** API Key 无效 / 鉴权失败（阿里云百炼 181001 即 API Key 无效） */
const API_KEY_PATTERNS = [
  /invalid[ _-]?api[ _-]?key/i,
  /api[ _-]?key[^，。；,;]{0,24}(invalid|wrong|error|incorrect|missing|not\s*found|no\s*found)/i,
  /authenticationerror/i,
  /unauthorized/i,
  /\[181001\]/,
  /error\s*code[:：]?\s*401/i,
  /401\s*(unauthorized|invalid|forbidden)/i,
];

/** 上下文超长 */
const CONTEXT_LIMIT_PATTERNS = [
  /context\s*(length|window|limit)/i,
  /token\s*limit/i,
  /maximum\s*(context|token)/i,
  /too\s*many\s*tokens/i,
  /exceed(ed|s)?\s*(the\s*)?(context|token)/i,
  /\[181006\]/,
  /\[181007\]/,
];

/** 请求过于频繁（限流） */
const RATE_LIMIT_PATTERNS = [
  /rate\s*limit/i,
  /too\s*many\s*requests/i,
  /throttl/i,
  /slow\s*down/i,
  /\[181003\]/,
];

/** 内容安全审查 */
const CONTENT_FILTER_PATTERNS = [
  /content\s*(filter|policy|moderat)/i,
  /moderat/i,
  /sensitive/i,
  /blocked\s*by\s*polic/i,
  /risk\s*control/i,
  /安全审查/i,
  /敏感词/i,
];

/** 请求超时 */
const TIMEOUT_PATTERNS = [
  /timeout/i,
  /timed?\s*out/i,
  /etimedout/i,
  /ec\s*onn?aborted/i,
  /socket\s*hang\s*up/i,
  /read\s*timeout/i,
  /deadline\s*exceeded/i,
  /gateway\s*timeout/i,
  /请求超时/i,
];

/** 网络连接失败 */
const NETWORK_PATTERNS = [
  /ec\s*onnrefused/i,
  /ec\s*onnreset/i,
  /connection\s*(refused|reset|closed|lost|error)/i,
  /network\s*error/i,
  /networkerror/i,
  /failed\s*to\s*fetch/i,
  /fetch\s*failed/i,
  /unable\s*to\s*connect/i,
  /could\s*not\s*connect/i,
  /websocket\s*(closed|error|failed|disconnect)/i,
  /网络连接/i,
];

/** 模型不存在 / 不可用 */
const MODEL_PATTERNS = [
  /model\s*(not\s*found|does\s*not\s*exist|invalid|unavailable|not\s*supported)/i,
  /unknown\s*model/i,
  /no\s*model\s*(found|available)/i,
  /\[181002\]/,
];

/** 技术特征：命中则认为该消息是面向排障的原始信息 */
const TECH_CHARS = /[{}[\]]|\\n|\\"|request_id|message_id|traceback|at\s+[A-Za-z_][\w.]*\(/;

/** 短小的、不含技术特征的文案（如后端直接返回的友好提示）直接透传 */
function looksHumanFriendly(message: string): boolean {
  return message.length <= 60 && !/[:：]/.test(message) && !TECH_CHARS.test(message);
}

export function humanizeError(raw: string | unknown): HumanizedError {
  const message = typeof raw === 'string' && raw.trim() ? raw.trim() : '';
  if (!message) {
    return { title: FALLBACK_ERROR_TITLE };
  }

  if (matchAny(message, API_KEY_PATTERNS)) {
    return { title: '模型服务鉴权失败，请检查 API Key 配置后重试', detail: message };
  }
  if (matchAny(message, CONTEXT_LIMIT_PATTERNS)) {
    return { title: '对话内容过长，请开启新对话或精简内容后重试', detail: message };
  }
  if (matchAny(message, RATE_LIMIT_PATTERNS)) {
    return { title: '请求过于频繁，请稍后再试', detail: message };
  }
  if (matchAny(message, CONTENT_FILTER_PATTERNS)) {
    return { title: '内容未通过安全审查，请调整表述后重试', detail: message };
  }
  if (matchAny(message, TIMEOUT_PATTERNS)) {
    return { title: '请求超时，请稍后重试', detail: message };
  }
  if (matchAny(message, NETWORK_PATTERNS)) {
    return { title: '网络连接失败，请检查网络后重试', detail: message };
  }
  if (matchAny(message, MODEL_PATTERNS)) {
    return { title: '模型不存在或不可用，请切换模型后重试', detail: message };
  }
  if (looksHumanFriendly(message)) {
    return { title: message };
  }
  return { title: FALLBACK_ERROR_TITLE, detail: message };
}
