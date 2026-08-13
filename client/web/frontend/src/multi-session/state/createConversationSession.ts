/**
 * session.create 创建会话：session_id 由后端生成并通过响应返回，前端不再传 session_id。
 *
 * 加长超时（Gateway→AgentServer unary 可达 600s）；超时后用同一个 create_token
 * 幂等重试——AgentServer 按 (create_token, session 参数签名) 返回同一个 session，
 * 避免超时后前后端会话分叉。
 */

import type { WorkMode } from '../../features/workspace/projectTypes';

export const SESSION_CREATE_TIMEOUT_MS = 60_000;

/** 超时后重试 session.create 的次数。 */
export const SESSION_CREATE_RETRY_ATTEMPTS = 3;

/** 重试间隔：给仍在飞行的 create 留出落盘时间，降低并发重复创建的几率。 */
export const SESSION_CREATE_RETRY_INTERVAL_MS = 1000;

export type SessionCreateRequestFn = <T = unknown>(
  method: string,
  params?: Record<string, unknown>,
  options?: { timeoutMs?: number },
) => Promise<T>;

export interface SessionCreatePayload {
  session_id?: string;
  sessionId?: string;
  project_id?: string;
  projectId?: string;
  project_dir?: string;
  projectDir?: string;
  work_mode?: WorkMode | string;
  workMode?: WorkMode | string;
}

export interface CreatedConversationSession {
  session_id: string;
  project_id?: string;
  project_dir?: string;
  work_mode?: WorkMode;
}

export interface CreateConversationSessionOptions {
  retryAttempts?: number;
  retryIntervalMs?: number;
  sleep?: (ms: number) => Promise<void>;
}

function normalizeWorkMode(value: unknown): WorkMode | undefined {
  return value === 'work' || value === 'code' ? value : undefined;
}

function errorCode(error: unknown): string | undefined {
  if (!error || typeof error !== 'object') return undefined;
  const code = (error as { code?: unknown }).code;
  return typeof code === 'string' ? code : undefined;
}

export function isRequestTimeoutError(error: unknown): boolean {
  return errorCode(error) === 'REQUEST_TIMEOUT';
}

export function resolveCreatedSessionId(
  payload: SessionCreatePayload | null | undefined,
): string | undefined {
  if (!payload) return undefined;
  const direct = payload.session_id ?? payload.sessionId;
  if (typeof direct === 'string' && direct.trim()) {
    return direct.trim();
  }
  return undefined;
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function invokeSessionCreate(
  request: SessionCreateRequestFn,
  createParams: Record<string, unknown>,
  createToken: string,
): Promise<CreatedConversationSession> {
  // session_id 必须由后端生成：显式剔除，避免旧逻辑误传。
  // create_token 由前端每次“逻辑创建”生成并跨重试复用，AgentServer 凭它做幂等。
  const params: Record<string, unknown> = { ...createParams, create_token: createToken };
  delete params.session_id;

  const payload = await request<SessionCreatePayload>('session.create', params, {
    timeoutMs: SESSION_CREATE_TIMEOUT_MS,
  });
  const createdSessionId = resolveCreatedSessionId(payload);
  if (!createdSessionId) {
    throw new Error('session.create did not return a session id');
  }
  return {
    session_id: createdSessionId,
    project_id: payload?.project_id ?? payload?.projectId,
    project_dir: payload?.project_dir ?? payload?.projectDir,
    work_mode: normalizeWorkMode(payload?.work_mode ?? payload?.workMode),
  };
}

async function recoverAfterCreateTimeout(
  request: SessionCreateRequestFn,
  createParams: Record<string, unknown>,
  createToken: string,
  options: CreateConversationSessionOptions = {},
): Promise<CreatedConversationSession> {
  const retryAttempts = Math.max(
    1,
    options.retryAttempts ?? SESSION_CREATE_RETRY_ATTEMPTS,
  );
  const retryIntervalMs = Math.max(
    0,
    options.retryIntervalMs ?? SESSION_CREATE_RETRY_INTERVAL_MS,
  );
  const sleep = options.sleep ?? defaultSleep;

  let lastError: unknown = new Error('session.create timed out');
  for (let attempt = 0; attempt < retryAttempts; attempt += 1) {
    if (attempt > 0 && retryIntervalMs > 0) {
      await sleep(retryIntervalMs);
    }
    try {
      // 同一 create_token 重试：后端返回同一个 session，不会重复创建。
      return await invokeSessionCreate(request, createParams, createToken);
    } catch (error) {
      if (!isRequestTimeoutError(error)) {
        throw error;
      }
      lastError = error;
    }
  }
  throw lastError;
}

/**
 * 创建会话。后端生成 session_id 并通过响应返回；
 * 超时后按同一 create_token 幂等重试。
 */
export async function createConversationSession(
  request: SessionCreateRequestFn,
  createParams: Record<string, unknown>,
  createToken: string,
  options: CreateConversationSessionOptions = {},
): Promise<CreatedConversationSession> {
  try {
    return await invokeSessionCreate(request, createParams, createToken);
  } catch (error) {
    if (!isRequestTimeoutError(error)) {
      throw error;
    }
    return recoverAfterCreateTimeout(request, createParams, createToken, options);
  }
}
