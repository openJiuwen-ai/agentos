/**
 * 将 jiuwenswarm `project.create` 错误映射为 i18n key。
 * 对照：jiuwenswarm/.../projectCreateErrors.ts
 */
export function projectCreateErrorKey(error: unknown): string | null {
  const message = error instanceof Error ? error.message : String(error);
  if (message.includes('project_dir already exists')) {
    return 'multiSession.project.errors.pathExists';
  }
  if (message.includes('project name already exists')) {
    return 'multiSession.project.errors.nameExists';
  }
  if (
    message.includes('project_dir does not exist')
    || message.includes('directory does not exist')
    || message.includes('path does not exist')
  ) {
    return 'multiSession.project.errors.pathMissing';
  }
  return null;
}
