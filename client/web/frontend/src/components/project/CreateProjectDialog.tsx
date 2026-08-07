import { useEffect, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import {
  getDirectoryName,
  isProjectDirectoryPickerSupported,
  selectProjectDirectory,
} from '../../features/workspace/projectDirectoryPicker';
import { SelectProjectPathIcon } from './projectIcons';
import './CreateProjectDialog.css';

export type CreateProjectDialogProps = {
  open: boolean;
  error?: string | null;
  submitting?: boolean;
  onCancel: () => void;
  onSubmit: (name: string, projectDir: string) => void | Promise<void>;
};

export function CreateProjectDialog({
  open,
  error = null,
  submitting = false,
  onCancel,
  onSubmit,
}: CreateProjectDialogProps) {
  const { t } = useTranslation();
  const titleId = useId();
  const [name, setName] = useState('');
  const [projectDir, setProjectDir] = useState('');
  const [picking, setPicking] = useState(false);
  const [pickerHint, setPickerHint] = useState<string | null>(null);
  const canSubmit = Boolean(name.trim()) && !submitting && !picking;
  const pickerSupported = isProjectDirectoryPickerSupported();

  useEffect(() => {
    if (!open) return;
    setName('');
    setProjectDir('');
    setPickerHint(null);
    setPicking(false);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !submitting && !picking) onCancel();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, submitting, picking, onCancel]);

  if (!open) return null;

  async function handlePickDirectory() {
    setPickerHint(null);
    if (!pickerSupported) {
      setPickerHint(t('multiSession.project.directoryPickerUnsupported'));
      return;
    }

    setPicking(true);
    try {
      const result = await selectProjectDirectory();
      if (!result.ok) {
        if (result.reason === 'cancelled') return;
        if (result.reason === 'unsupported') {
          setPickerHint(t('multiSession.project.directoryPickerUnsupported'));
          return;
        }
        setPickerHint(result.message || t('multiSession.project.directoryPickerFailed'));
        return;
      }
      setProjectDir(result.path);
      setName((prev) => prev.trim() || result.name || getDirectoryName(result.path));
    } finally {
      setPicking(false);
    }
  }

  return (
    <div
      className="create-project-dialog__backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !submitting && !picking) onCancel();
      }}
    >
      <form
        className="create-project-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onSubmit={(event) => {
          event.preventDefault();
          if (!canSubmit) return;
          void onSubmit(name.trim(), projectDir.trim());
        }}
      >
        <div className="create-project-dialog__header">
          <h2 id={titleId} className="create-project-dialog__title">
            {t('multiSession.project.newProject')}
          </h2>
          <button
            type="button"
            className="create-project-dialog__close"
            aria-label={t('common.close')}
            disabled={submitting || picking}
            onClick={onCancel}
          >
            <X size={18} strokeWidth={1.75} />
          </button>
        </div>

        <div className="create-project-dialog__body">
          <div className="create-project-dialog__field">
            <label className="create-project-dialog__label" htmlFor="create-project-name">
              <span>{t('multiSession.project.nameLabel', { defaultValue: '项目名称' })}</span>
              <span className="create-project-dialog__required" aria-hidden>
                *
              </span>
            </label>
            <input
              id="create-project-name"
              className="create-project-dialog__input"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t('multiSession.project.namePlaceholder')}
              autoFocus
              disabled={submitting || picking}
            />
          </div>

          {/* 路径：视觉跟稿（胶囊 + 文件夹），不加 *，逻辑仍选填 */}
          <div className="create-project-dialog__field">
            <label className="create-project-dialog__label" htmlFor="create-project-path">
              {t('multiSession.project.pathLabel', { defaultValue: '项目路径' })}
            </label>
            <div className="create-project-dialog__path-box">
              <button
                type="button"
                className="create-project-dialog__folder-btn"
                disabled={submitting || picking}
                title={t('multiSession.project.selectExisting')}
                aria-label={t('multiSession.project.selectExisting')}
                onClick={() => void handlePickDirectory()}
              >
                <SelectProjectPathIcon size={16} />
              </button>
              <input
                id="create-project-path"
                className="create-project-dialog__input create-project-dialog__input--path"
                value={projectDir}
                onChange={(event) => {
                  setProjectDir(event.target.value);
                  setPickerHint(null);
                }}
                placeholder={t('multiSession.project.pathPlaceholder', {
                  defaultValue: '选填，留空则自动创建；或粘贴绝对路径',
                })}
                disabled={submitting || picking}
              />
            </div>
            <p className="create-project-dialog__hint">
              {pickerSupported
                ? t('multiSession.project.pathHintDesktop', {
                    defaultValue: '点击左侧文件夹图标选择已有目录；留空则由后端自动创建',
                  })
                : t('multiSession.project.pathHintBrowser', {
                    defaultValue: '网页版请手动粘贴绝对路径，或使用桌面客户端点击文件夹图标选择',
                  })}
            </p>
            {pickerHint ? <p className="create-project-dialog__error">{pickerHint}</p> : null}
          </div>

          {error ? <p className="create-project-dialog__error">{error}</p> : null}
        </div>

        <div className="create-project-dialog__actions">
          <button
            type="button"
            className="create-project-dialog__btn create-project-dialog__btn--secondary"
            disabled={submitting || picking}
            onClick={onCancel}
          >
            {t('multiSession.project.cancel')}
          </button>
          <button
            type="submit"
            className="create-project-dialog__btn create-project-dialog__btn--primary"
            disabled={!canSubmit}
          >
            {submitting
              ? t('multiSession.project.creating', { defaultValue: '创建中…' })
              : t('multiSession.project.confirm')}
          </button>
        </div>
      </form>
    </div>
  );
}
