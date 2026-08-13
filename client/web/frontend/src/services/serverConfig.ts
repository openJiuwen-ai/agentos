/**
 * 远端服务器配置与鉴权服务（第二阶段）
 *
 * - /local-api/* 由 client 本地服务器（app_web.py / vite dev 插件）提供：
 *   服务器地址的保存、读取与连接测试（管理面 :8090 健康检查 + jiuwen 后端 :19000 TCP 探测）。
 * - /iam-api/* 代理到管理面 http://host:8090/api/v1/*，用于登录鉴权（001-iam-auth-v0）。
 */

export interface ServerEndpointResult {
  ok: boolean;
  error?: string;
}

export interface ServerTestResult {
  ok: boolean;
  host?: string;
  manager?: ServerEndpointResult;
  backend?: ServerEndpointResult;
  error?: string;
}

export interface AuthSession {
  access_token: string;
  refresh_token: string;
  user_id: string;
  username: string;
  role: string;
}

const AUTH_STORAGE_KEY = 'agentos_auth_session';

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = (await resp.json().catch(() => ({}))) as Record<string, unknown>;
  if (!resp.ok) {
    const detail =
      (typeof data.error === 'string' && data.error) ||
      (typeof data.detail === 'string' && data.detail) ||
      (typeof data.message === 'string' && data.message) ||
      `请求失败（HTTP ${resp.status}）`;
    throw new Error(detail);
  }
  return data as T;
}

/* ---------- 服务器配置 ---------- */

export async function getSavedServer(): Promise<{ address: string | null; host: string | null }> {
  try {
    const resp = await fetch('/local-api/server');
    if (!resp.ok) return { address: null, host: null };
    const data = (await resp.json()) as { address?: string | null; host?: string | null };
    return { address: data.address ?? null, host: data.host ?? null };
  } catch {
    return { address: null, host: null };
  }
}

export function testServer(address: string): Promise<ServerTestResult> {
  return postJson<ServerTestResult>('/local-api/server/test', { address });
}

export function saveServer(address: string): Promise<{ ok: boolean; host: string }> {
  return postJson<{ ok: boolean; host: string }>('/local-api/server', { address });
}

/* ---------- 登录鉴权（管理面 IAM） ---------- */

interface IamResponse {
  code: number;
  message?: string;
  data?: AuthSession;
}

async function iamAuthCall(path: string, body: unknown): Promise<AuthSession> {
  const resp = await fetch(`/iam-api/${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload = (await resp.json().catch(() => ({}))) as IamResponse & { detail?: string };
  if (!resp.ok) {
    throw new Error(payload.detail || payload.message || `鉴权请求失败（HTTP ${resp.status}）`);
  }
  if (!payload.data?.access_token) {
    throw new Error(payload.message || '管理面返回了无效的登录响应');
  }
  return payload.data;
}

export function iamLogin(username: string, password: string): Promise<AuthSession> {
  return iamAuthCall('auth/login', { username, password });
}

export function iamRefresh(refreshToken: string): Promise<AuthSession> {
  return iamAuthCall('auth/refresh', { refresh_token: refreshToken });
}

/** 吊销 refresh_token（尽力而为，失败不阻塞本地登出） */
export async function iamLogout(session: AuthSession): Promise<void> {
  try {
    await fetch('/iam-api/auth/logout', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({ refresh_token: session.refresh_token }),
    });
  } catch {
    /* 网络失败时仅清理本地会话 */
  }
}

/* ---------- 本地会话存取 ---------- */

export function getAuthSession(): AuthSession | null {
  try {
    const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AuthSession>;
    if (!parsed.access_token || !parsed.refresh_token || !parsed.username) return null;
    return parsed as AuthSession;
  } catch {
    return null;
  }
}

export function saveAuthSession(session: AuthSession): void {
  try {
    window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
  } catch {
    /* ignore */
  }
}

export function clearAuthSession(): void {
  try {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
