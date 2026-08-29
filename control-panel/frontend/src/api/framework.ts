import { post, get, put, del } from './index';

const BASE = '/api/v1/thirdparty_agent';

export interface CardItem {
  framework: string;
  framework_version: string;
  is_default?: boolean;
  total_instances?: number;
  running_instances?: number;
  package_path?: string;
}

export interface ListCardsParams {
  framework?: string;
  size?: number;
  page?: number;
}

export interface ListCardsResponse {
  items: CardItem[];
  total: number;
}

export interface PublishAccepted {
  digest: string;
  request_id: string;
}

export interface UnregisteredItem {
  digest: string;
  original_filename: string;
  package_path: string;
  locked: boolean;
  last_error?: string | null;
  request_id?: string | null;
  status?: string;
  progress?: number;
}

export function listCards(params: ListCardsParams = {}) {
  return get<ListCardsResponse>(`${BASE}/cards`, {
    framework: params.framework || '',
    size: params.size ?? 20,
    page: params.page ?? 1,
  });
}

export function getCard(framework: string, version: string) {
  return get<CardItem>(`${BASE}/cards/${encodeURIComponent(framework)}/${encodeURIComponent(version)}`);
}

export function publishCard(file: File, launchCommand: string) {
  const fd = new FormData();
  fd.append('package', file);
  fd.append('launch_command', launchCommand);
  return post<PublishAccepted>(`${BASE}/cards`, fd, {
    timeout: 60 * 60 * 1000,
  });
}

export function deleteCard(framework: string, version: string) {
  return del(`${BASE}/cards/${encodeURIComponent(framework)}/${encodeURIComponent(version)}`);
}

export function setDefaultVersion(framework: string, version: string) {
  return put(`${BASE}/cards/${encodeURIComponent(framework)}/default`, {
    framework_version: version,
  });
}

export function listUnregistered() {
  return get<{ items: UnregisteredItem[] }>(`${BASE}/unregistered`);
}

export function getUnregistered(digest: string) {
  return get<UnregisteredItem>(`${BASE}/unregistered/${digest}`);
}

export function retryUnregistered(digest: string, launchCommand: string) {
  const fd = new FormData();
  fd.append('launch_command', launchCommand);
  return post<PublishAccepted>(`${BASE}/unregistered/${digest}/retry`, fd);
}

export function deleteUnregistered(digest: string) {
  return del(`${BASE}/unregistered/${digest}`);
}

/** @deprecated use CardItem */
export type FrameworkItem = CardItem & { agent_name: string; version: string };
