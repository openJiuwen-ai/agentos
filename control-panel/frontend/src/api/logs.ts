import { get, del, post } from "./index";

export interface LogCategoryItem {
  key: string;
  label: string;
  count: number;
  component_id: string;
}

export interface LogComponent {
  id: string;
  category: string;
  name: string;
  log_path: string;
  description: string;
  size: number | null;
  created_at: string;
  updated_at: string;
}

export interface LogExportTask {
  task_id: string;
  task_type: "export" | "archive";
  component_id: string | null;
  component_name: string;
  component_category: string;
  source_path: string | null;
  source_name: string | null;
  line_count: number | null;
  status: "pending" | "running" | "completed" | "failed";
  file_path: string | null;
  file_size_bytes: number | null;
  error_message: string | null;
  created_by: string;
  created_at: string;
  completed_at: string | null;
}

export interface FileEntry {
  name: string;
  path: string;
  size: number;
  modified: string;
  is_dir: boolean;
}

const BASE = "/api/v1/logs";

export function getLogCategories(): Promise<LogCategoryItem[]> {
  return get<LogCategoryItem[]>(`${BASE}/categories`);
}

export function getLogComponents(category?: string): Promise<LogComponent[]> {
  return get<LogComponent[]>(
    `${BASE}/components`,
    category ? { category } : undefined,
  );
}

export function getLokiFilenames(
  ip: string,
  category?: string,
): Promise<string[]> {
  return get<string[]>(`${BASE}/loki/filenames`, {
    ip,
    ...(category ? { category } : {}),
  });
}

export function resolveFilePath(
  componentId: string,
  subpath: string,
): Promise<{ resolved_path: string }> {
  return get<{ resolved_path: string }>(
    `${BASE}/components/${componentId}/resolve-path`,
    { subpath },
  );
}

export interface LokiExportParams {
  category?: string;
  keyword?: string;
  host?: string;
  ip?: string;
  filename?: string;
  start: string;
  end: string;
  limit?: number;
}

export function createLokiExport(
  data: LokiExportParams,
): Promise<{ task_id: string; status: string }> {
  return post<{ task_id: string; status: string }>(`${BASE}/loki/export`, data);
}

export function getExports(): Promise<LogExportTask[]> {
  return get<LogExportTask[]>(`${BASE}/exports`);
}

export function getExportStatus(taskId: string): Promise<LogExportTask> {
  return get<LogExportTask>(`${BASE}/exports/${taskId}`);
}

export function getExportDownloadUrl(taskId: string): string {
  return `${BASE}/exports/${taskId}/download`;
}

export function deleteExport(taskId: string): Promise<void> {
  return del<void>(`${BASE}/exports/${taskId}`);
}
