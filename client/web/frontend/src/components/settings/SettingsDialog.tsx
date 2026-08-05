/**
 * 设置弹窗 —— 界面语言 / 权限（主题当前仅浅色）
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Globe, ShieldCheck, ShieldAlert, Palette } from 'lucide-react';
import type { Permission } from '../../types';

export function SettingsDialog({
  permission,
  onChangePermission,
  onClose,
}: {
  permission: Permission;
  onChangePermission: (permission: Permission) => void;
  onClose: () => void;
}) {
  const { i18n } = useTranslation();
  const [lang, setLang] = useState(i18n.language?.startsWith('en') ? 'en' : 'zh');

  const handleLang = (value: 'zh' | 'en') => {
    setLang(value);
    void i18n.changeLanguage(value === 'en' ? 'en' : 'zh');
    try {
      window.localStorage.setItem('agentos_lang', value);
    } catch { /* ignore */ }
  };

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div className="modal-title">设置</div>
          <button className="icon-btn icon-btn--sm" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <section>
            <div className="settings-section-title"><Palette size={14} /> 主题</div>
            <div className="settings-options">
              <button className="settings-option is-active">浅色</button>
              <button className="settings-option" disabled title="即将上线">深色</button>
            </div>
          </section>

          <section>
            <div className="settings-section-title"><Globe size={14} /> 界面语言</div>
            <div className="settings-options">
              <button className={`settings-option ${lang === 'zh' ? 'is-active' : ''}`} onClick={() => handleLang('zh')}>简体中文</button>
              <button className={`settings-option ${lang === 'en' ? 'is-active' : ''}`} onClick={() => handleLang('en')}>English</button>
            </div>
          </section>

          <section>
            <div className="settings-section-title"><ShieldCheck size={14} /> 权限</div>
            <div className="settings-options">
              <button
                className={`settings-option ${permission === 'default' ? 'is-active' : ''}`}
                onClick={() => onChangePermission('default')}
              >
                <ShieldCheck size={13} /> 默认权限
              </button>
              <button
                className={`settings-option ${permission === 'full_access' ? 'is-active' : ''}`}
                onClick={() => onChangePermission('full_access')}
              >
                <ShieldAlert size={13} /> 完全访问权限
              </button>
            </div>
            <p className="settings-hint">完全访问权限下，敏感操作将不再逐项请求确认。</p>
          </section>
        </div>
        <div className="modal-foot">
          <button className="btn btn-primary" onClick={onClose}>完成</button>
        </div>
      </div>
    </div>
  );
}

export function PluginsDialog({ onClose }: { onClose: () => void }) {
  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div className="modal-title">插件</div>
          <button className="icon-btn icon-btn--sm" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="modal-body">
          <div className="empty-hint" style={{ padding: '40px 0' }}>插件功能即将上线，敬请期待</div>
        </div>
        <div className="modal-foot">
          <button className="btn btn-primary" onClick={onClose}>知道了</button>
        </div>
      </div>
    </div>
  );
}
