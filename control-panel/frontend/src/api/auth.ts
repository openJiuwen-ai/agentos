import { get, post } from './index';

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  user_id: string;
  username: string;
  role: string;
}

/** POST /api/v1/auth/login — returns token pair on success */
export function login(username: string, password: string): Promise<LoginResponse> {
  return post<LoginResponse>('/api/v1/auth/login', { username, password });
}

// ── OAuth2 ────────────────────────────────────────────────────────────

export interface OAuthDecisionParams {
  action: 'allow' | 'deny';
  client_id: string;
  redirect_uri: string;
  state: string;
}

export interface OAuthDecisionResponse {
  redirect_uri: string;
}

export function submitOAuthDecision(params: OAuthDecisionParams): Promise<OAuthDecisionResponse> {
  return post<OAuthDecisionResponse>('/api/v1/oauth2/authorize', params);
}

// ── Permissions ───────────────────────────────────────────────────────

export interface PermissionsResponse {
  user_id: string;
  username: string;
  role: string;
  permissions: Record<string, string[]>;
}

/** GET /api/v1/auth/permissions — verify the access token is still valid and
 * return the full permission matrix for the current user. Throws on 401/403
 * so the caller can treat a thrown error as "token invalid, must log in". */
export function getPermissions(): Promise<PermissionsResponse> {
  return get<PermissionsResponse>('/api/v1/auth/permissions');
}
