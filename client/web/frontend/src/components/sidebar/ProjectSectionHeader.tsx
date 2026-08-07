import { useTranslation } from 'react-i18next';
import { NewProjectIcon } from '../project/projectIcons';

export type ProjectSectionHeaderProps = {
  onCreateClick: () => void;
};

export function ProjectSectionHeader({ onCreateClick }: ProjectSectionHeaderProps) {
  const { t } = useTranslation();
  return (
    <div className="project-section-header">
      <span className="project-section-header__title">{t('multiSession.project.projects')}</span>
      <button
        type="button"
        className="project-section-header__add"
        aria-label={t('multiSession.project.newProject')}
        title={t('multiSession.project.newProject')}
        onClick={onCreateClick}
      >
        <NewProjectIcon size={16} />
      </button>
    </div>
  );
}
