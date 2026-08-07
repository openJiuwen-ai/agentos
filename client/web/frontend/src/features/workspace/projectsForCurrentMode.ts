import type { ProjectInfo, WorkMode } from './projectTypes';

/** 按当前 work_mode 过滤可见项目（新增辅助函数，未改 workspaceStore） */
export function projectsForCurrentMode(
  projects: ProjectInfo[],
  workMode: WorkMode,
): ProjectInfo[] {
  return projects.filter((p) => !p.hidden && p.work_mode === workMode);
}
