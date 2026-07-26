import { get, post, put, patch, del } from './index';

export interface UserItem {
  user_id: string;
  username: string;
  role: string;
  is_active: boolean;
  created_at: string | null;
}

export interface PaginatedUsers {
  total: number;
  items: UserItem[];
}

export interface BatchCreateResult {
  username: string;
  user_id: string | null;
  password: string | null;
  error: string | null;
}

export interface UserProfile {
  user_id: string;
  username: string;
  role: string;
  is_active: boolean;
  created_at: string | null;
}

/** GET /api/v1/users — admin: paginated user list */
export function getUsers(params?: {
  page?: number;
  page_size?: number;
  sort?: string;
  order?: string;
  search?: string;
  role?: string;
  is_active?: string | null;
}): Promise<PaginatedUsers> {
  return get<PaginatedUsers>('/api/v1/users', params);
}

/** POST /api/v1/users/batch — admin: batch create users */
export function batchCreateUsers(usernames: string[]): Promise<BatchCreateResult[]> {
  return post<BatchCreateResult[]>('/api/v1/users/batch', { usernames });
}

/** GET /api/v1/users/me — current user profile */
export function getMe(): Promise<UserProfile> {
  return get<UserProfile>('/api/v1/users/me');
}

/** PUT /api/v1/users/me/password — change own password */
export function changeMyPassword(old_password: string, new_password: string): Promise<void> {
  return put<void>('/api/v1/users/me/password', { old_password, new_password });
}

/** POST /api/v1/users/:id/reset-password — admin: reset user password */
export function resetUserPassword(user_id: string): Promise<{ user_id: string; username: string; new_password: string }> {
  return post<{ user_id: string; username: string; new_password: string }>(`/api/v1/users/${user_id}/reset-password`);
}

/** PATCH /api/v1/users/:id — admin: update user (role escalation disabled; only is_active allowed) */
export function updateUser(user_id: string, data: { is_active?: boolean }): Promise<UserItem> {
  return patch<UserItem>(`/api/v1/users/${user_id}`, data);
}

/** DELETE /api/v1/users/:id — admin: delete user */
export function deleteUser(user_id: string): Promise<void> {
  return del<void>(`/api/v1/users/${user_id}`);
}
