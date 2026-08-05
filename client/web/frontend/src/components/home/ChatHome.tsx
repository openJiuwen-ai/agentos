/**
 * 对话首页 —— 按 UI_design/对话-首页 设计稿实现
 * 日常办公/代码开发 切换 + slogan + IP 形象 + 输入框 + 推荐技能
 */
import { useEffect, useState } from 'react';
import { Briefcase, Code2, FileText, Presentation, Table2, Mail, FileSearch, Image } from 'lucide-react';
import { useChatStore, useSessionStore, useWorkspaceStore } from '../../stores';
import { webRequest } from '../../services/webClient';
import { NEW_CONVERSATION_ID } from '../../multi-session/state/newConversationLifecycle';
import { Composer, type ComposerProps } from '../composer/Composer';
import mascot from '../../assets/design/mascot.png';
import './ChatHome.css';

interface SkillItem {
  name: string;
  display_name?: string;
  enabled?: boolean;
  installed?: boolean;
}

const RECOMMENDED_SKILLS = [
  { label: '文档', icon: FileText, match: /doc|文档|word/i },
  { label: '幻灯片', icon: Presentation, match: /ppt|幻灯|slide|presentation/i },
  { label: '表格', icon: Table2, match: /excel|表格|sheet|spreadsheet/i },
  { label: '邮件', icon: Mail, match: /mail|邮件|email/i },
  { label: '调研报告', icon: FileSearch, match: /report|调研|research/i },
  { label: '图片生成', icon: Image, match: /image|图片|图画|draw/i },
];

export function ChatHome(props: Omit<ComposerProps, 'sessionId' | 'variant'>) {
  const workMode = useWorkspaceStore((s) => s.workMode);
  const setWorkMode = useWorkspaceStore((s) => s.setWorkMode);
  const loadProjects = useWorkspaceStore((s) => s.loadProjects);
  const addSelectedSkill = useSessionStore((s) => s.addSelectedSkill);
  const [skills, setSkills] = useState<SkillItem[]>([]);

  useEffect(() => {
    webRequest<{ skills?: SkillItem[] }>('skills.list', { with_installed: true }, { timeoutMs: 30_000 })
      .then((data) => setSkills((data.skills ?? []).filter((s) => s.installed !== false && s.enabled !== false)))
      .catch(() => setSkills([]));
  }, []);

  const handleModeChange = (mode: 'work' | 'code') => {
    if (mode === workMode) return;
    void setWorkMode(mode).then(() => loadProjects());
  };

  const handleSkillChip = (chip: (typeof RECOMMENDED_SKILLS)[number]) => {
    const matched = skills.find((s) => chip.match.test(s.name) || (s.display_name && chip.match.test(s.display_name)));
    if (matched) {
      addSelectedSkill(NEW_CONVERSATION_ID, matched.name);
      return;
    }
    // 未安装对应技能时，填入提示语引导模型
    const current = useChatStore.getState().getRuntime(NEW_CONVERSATION_ID)?.inputValue ?? '';
    useChatStore.getState().setInputValue(
      NEW_CONVERSATION_ID,
      current ? `${current}，帮我处理${chip.label}相关的工作` : `帮我处理${chip.label}相关的工作`,
    );
  };

  return (
    <div className="home">
      <div className="home-content">
        <div className="home-top">
          <div className="home-mode-toggle">
            <button
              className={`home-mode-btn ${workMode === 'work' ? 'is-active' : ''}`}
              onClick={() => handleModeChange('work')}
            >
              <Briefcase size={15} />
              <span>日常办公</span>
            </button>
            <button
              className={`home-mode-btn ${workMode === 'code' ? 'is-active' : ''}`}
              onClick={() => handleModeChange('code')}
            >
              <Code2 size={15} />
              <span>代码开发</span>
            </button>
          </div>
          <div className="home-hero">
            <h1 className="home-slogan">和智能体一起，<br />把想法变成结果</h1>
            <img src={mascot} alt="" className="home-mascot" />
          </div>
        </div>

        <Composer {...props} sessionId={NEW_CONVERSATION_ID} variant="home" />

        <div className="home-skills">
          {RECOMMENDED_SKILLS.map((chip) => (
            <button key={chip.label} className="home-skill-chip" onClick={() => handleSkillChip(chip)}>
              <chip.icon size={15} />
              <span>{chip.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
