import { post } from './index';

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
