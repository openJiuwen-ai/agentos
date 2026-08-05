/**
 * 登录页 —— 按 UI_design/登录页 设计稿实现
 * 纯前端校验（无后端鉴权），任意非空账号名 + 密码即可进入
 */
import { useState } from 'react';
import loginHero from '../../assets/design/login-hero.png';
import './LoginPage.css';

export const LOGIN_STORAGE_KEY = 'agentos_login_user';

export function getLoginUser(): string | null {
  try {
    return window.localStorage.getItem(LOGIN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function clearLoginUser(): void {
  try {
    window.localStorage.removeItem(LOGIN_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

function LogoMark() {
  return (
    <div className="login-logo" aria-hidden="true">
      <svg width="34" height="34" viewBox="0 0 34 34" fill="none">
        <path
          d="M17 3L28.5 9.6v13.2L17 31 5.5 22.8V9.6L17 3Z"
          stroke="#fff"
          strokeWidth="2.2"
          strokeLinejoin="round"
        />
        <circle cx="17" cy="14.5" r="3.2" fill="#fff" />
        <path d="M9.5 24.5c2-3.6 4.7-5.4 7.5-5.4s5.5 1.8 7.5 5.4" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </div>
  );
}

export function LoginPage({ onLogin }: { onLogin: (username: string) => void }) {
  const [account, setAccount] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (event?: React.FormEvent) => {
    event?.preventDefault();
    if (!account.trim()) {
      setError('请输入账号名');
      return;
    }
    if (!password) {
      setError('请输入密码');
      return;
    }
    try {
      window.localStorage.setItem(LOGIN_STORAGE_KEY, account.trim());
    } catch {
      /* ignore */
    }
    onLogin(account.trim());
  };

  return (
    <div className="login-page">
      <div className="login-left">
        <form className="login-form" onSubmit={handleSubmit}>
          <LogoMark />
          <h1 className="login-title">欢迎使用华为智能体一体机</h1>
          <p className="login-desc">通过本地部署的 AI 能力，协助你处理日常工作、编写代码并完成复杂任务。</p>

          <label className="login-label" htmlFor="login-account">账号名</label>
          <input
            id="login-account"
            className="login-input"
            placeholder="请输入账号名"
            value={account}
            autoComplete="username"
            onChange={(e) => { setAccount(e.target.value); setError(''); }}
          />

          <label className="login-label" htmlFor="login-password">密码</label>
          <input
            id="login-password"
            className="login-input"
            type="password"
            placeholder="请输入密码"
            value={password}
            autoComplete="current-password"
            onChange={(e) => { setPassword(e.target.value); setError(''); }}
          />

          {error ? <div className="login-error">{error}</div> : null}

          <button type="submit" className="login-submit">登录</button>
          <div className="login-tip">暂无账号？请联系系统管理员</div>
        </form>
      </div>
      <div className="login-right">
        <img src={loginHero} alt="" className="login-hero" />
      </div>
    </div>
  );
}
