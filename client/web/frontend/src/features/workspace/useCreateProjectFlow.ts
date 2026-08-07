import { useCallback, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { isLikelyAbsolutePath } from './projectDirectoryPicker';
import { projectCreateErrorKey } from './projectCreateErrors';
import type { ProjectInfo } from './projectTypes';
import { webClient } from '../../services/webClient';
import { useWorkspaceStore } from '../../stores/workspaceStore';

type CreateProjectFlowOptions = {
  onSuccess?: (project: ProjectInfo) => void;
};

/**
 * 创建项目弹窗 ↔ jiuwenswarm WS RPC（project.create / project.list）联动。
 *
 * 调用链：
 * submit → workspaceStore.createProject
 *        → projectRegistryClient.create('project.create')
 *        → loadProjects('project.list')
 *        → loadProjectSessions('project.get_sessions')
 */
export function useCreateProjectFlow(options: CreateProjectFlowOptions = {}) {
  const { t } = useTranslation();
  const onSuccessRef = useRef(options.onSuccess);
  onSuccessRef.current = options.onSuccess;

  const projects = useWorkspaceStore((s) => s.projects);
  const workMode = useWorkspaceStore((s) => s.workMode);
  const createProject = useWorkspaceStore((s) => s.createProject);
  const loadProjectSessions = useWorkspaceStore((s) => s.loadProjectSessions);

  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const openDialog = useCallback(() => {
    setError(null);
    setOpen(true);
  }, []);

  const closeDialog = useCallback(() => {
    if (submitting) return;
    setOpen(false);
    setError(null);
  }, [submitting]);

  const resolveError = useCallback(
    (err: unknown): string => {
      const key = projectCreateErrorKey(err);
      if (key) return t(key);
      return err instanceof Error ? err.message : String(err);
    },
    [t],
  );

  const submit = useCallback(
    async (name: string, projectDir: string) => {
      setError(null);

      // webClient 成功态为 'ready'（见 WebConnectionState），不是 'connected'
      if (webClient.getState() !== 'ready') {
        setError('未连接后端，请确认 jiuwenswarm Web 服务已启动（默认 127.0.0.1:19000），或点击页面上的重连');
        return;
      }

      const trimmedName = name.trim();
      // 空路径传 ""，由后端自动创建目录（jiuwenswarm project.create 约定）
      const trimmedDir = projectDir.trim();

      if (!trimmedName) {
        setError(t('multiSession.project.namePlaceholder'));
        return;
      }

      if (trimmedDir && !isLikelyAbsolutePath(trimmedDir)) {
        setError(t('multiSession.project.absolutePathError'));
        return;
      }

      const dup = projects.some(
        (p) => !p.hidden && (p.work_mode ?? workMode) === workMode && p.name === trimmedName,
      );
      if (dup) {
        setError(t('multiSession.project.errors.nameExists'));
        return;
      }

      setSubmitting(true);
      try {
        const project = await createProject(trimmedName, trimmedDir);
        setOpen(false);
        void loadProjectSessions(project.project_id);
        onSuccessRef.current?.(project);
      } catch (err) {
        setError(resolveError(err));
      } finally {
        setSubmitting(false);
      }
    },
    [createProject, loadProjectSessions, projects, resolveError, t, workMode],
  );

  return {
    open,
    submitting,
    error,
    openDialog,
    closeDialog,
    submit,
  };
}
