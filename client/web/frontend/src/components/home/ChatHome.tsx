/**
 * 对话首页 —— 按 对话-首页 设计稿实现
 * 结构: hero(slogan形象 + 模式切换) —[110px]— input-area(输入框 —[32px]— 推荐技能)
 * 形象绝对定位浮在内容区右侧
 */
import { useEffect, useState } from 'react';
import { useChatStore, useSessionStore, useWorkspaceStore } from '../../stores';
import { webRequest } from '../../services/webClient';
import { NEW_CONVERSATION_ID } from '../../multi-session/state/newConversationLifecycle';
import { Composer, type ComposerProps } from '../composer/Composer';
import './ChatHome.css';

// slogan（设计稿 PNG，字体无法用 CSS 复刻）
import sloganImg from '../../assets/design/home/slogan.png';
// 首页形象
import heroImage from '../../assets/design/home/home-mascot.svg';
// 模式切换图标（选中 / 未选中 两态）
import workActive from '../../assets/design/home/work-active.svg';
import workInactive from '../../assets/design/home/work-inactive.svg';
import codeActive from '../../assets/design/home/code-active.svg';
import codeInactive from '../../assets/design/home/code-inactive.svg';
// 推荐技能图标
import docIcon from '../../assets/design/home/document.svg';
import slideIcon from '../../assets/design/home/slides.svg';
import tableIcon from '../../assets/design/home/table.svg';
import mailIcon from '../../assets/design/home/email.svg';
import reportIcon from '../../assets/design/home/research-report.svg';
import imageGenIcon from '../../assets/design/home/image-gen.svg';

interface SkillItem {
  name: string;
  display_name?: string;
  enabled?: boolean;
  installed?: boolean;
}

const RECOMMENDED_SKILLS = [
  { label: '文档', icon: docIcon, match: /doc|文档|word/i },
  { label: '幻灯片', icon: slideIcon, match: /ppt|幻灯|slide|presentation/i },
  { label: '表格', icon: tableIcon, match: /excel|表格|sheet|spreadsheet/i },
  { label: '邮件', icon: mailIcon, match: /mail|邮件|email/i },
  { label: '调研报告', icon: reportIcon, match: /report|调研|research/i },
  { label: '图片生成', icon: imageGenIcon, match: /image|图片|图画|draw/i },
];

export function ChatHome(props: Omit<ComposerProps, 'sessionId' | 'variant'>) {
  const workMode = useWorkspaceStore(s => s.workMode);
  const setWorkMode = useWorkspaceStore(s => s.setWorkMode);
  const loadProjects = useWorkspaceStore(s => s.loadProjects);
  const addSelectedSkill = useSessionStore(s => s.addSelectedSkill);
  const [skills, setSkills] = useState<SkillItem[]>([]);

  useEffect(() => {
    webRequest<{ skills?: SkillItem[] }>('skills.list', { with_installed: true }, { timeoutMs: 30_000 })
      .then(data => setSkills((data.skills ?? []).filter(s => s.installed !== false && s.enabled !== false)))
      .catch(() => setSkills([]));
  }, []);

  const handleModeChange = (mode: 'work' | 'code') => {
    if (mode === workMode) return;
    void setWorkMode(mode).then(() => loadProjects());
  };

  const handleSkillChip = (chip: (typeof RECOMMENDED_SKILLS)[number]) => {
    const matched = skills.find(s => chip.match.test(s.name) || (s.display_name && chip.match.test(s.display_name)));
    if (matched) {
      addSelectedSkill(NEW_CONVERSATION_ID, matched.name);
      return;
    }
    // 未安装对应技能时，填入提示语引导模型
    const current = useChatStore.getState().getRuntime(NEW_CONVERSATION_ID)?.inputValue ?? '';
    useChatStore.getState().setInputValue(NEW_CONVERSATION_ID, current ? `${current}，帮我处理${chip.label}相关的工作` : `帮我处理${chip.label}相关的工作`);
  };

  return (
    <div className="home">
      <div className="home-content">
        {/* hero: slogan + 模式切换 */}
        <div className="home-hero">
          <img src={sloganImg} alt="你的AI办公搭子" className="home-slogan" />
          <div className="home-mode-toggle">
            <button className={`home-mode-btn ${workMode === 'work' ? 'is-active' : ''}`} onClick={() => handleModeChange('work')}>
              <img src={workMode === 'work' ? workActive : workInactive} alt="" className="home-mode-icon" />
              <span>日常办公</span>
            </button>
            <button className={`home-mode-btn ${workMode === 'code' ? 'is-active' : ''}`} onClick={() => handleModeChange('code')}>
              <img src={workMode === 'code' ? codeActive : codeInactive} alt="" className="home-mode-icon" />
              <span>代码开发</span>
            </button>
          </div>
        </div>

        {/* input-area: 输入框 + 推荐技能 */}
        <div className="home-input-area">
          <div className="home-composer-wrap">
            {/* 首页形象 —— 底边与输入框顶部重叠 25px（设计稿 DSL 精确值） */}
            <img src={heroImage} alt="" className="home-mascot" />

            <Composer {...props} sessionId={NEW_CONVERSATION_ID} variant="home" />
          </div>

          <div className="home-skills">
            {RECOMMENDED_SKILLS.map(chip => (
              <button key={chip.label} className="home-skill-chip" onClick={() => handleSkillChip(chip)}>
                <img src={chip.icon} alt="" className="home-skill-icon" />
                <span>{chip.label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
