/**
 * 登录页 —— 按 UI_design/登录页 设计稿实现
 * 第二阶段：对接管理面 IAM 鉴权（POST /api/v1/auth/login，见 001-iam-auth-v0.md），
 * 成功返回 access_token + refresh_token + user 信息并保存本地会话；失败展示错误信息允许重试。
 */
import { useState } from 'react';
import loginHero from '../../assets/design/login-hero.png';
import {
  clearAuthSession,
  getAuthSession,
  iamLogin,
  saveAuthSession,
} from '../../services/serverConfig';
import './LoginPage.css';

export function getLoginUser(): string | null {
  return getAuthSession()?.username ?? null;
}

export function clearLoginUser(): void {
  clearAuthSession();
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
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (event?: React.FormEvent) => {
    event?.preventDefault();
    const username = account.trim();
    if (!username) {
      setError('请输入账号名');
      return;
    }
    if (!password) {
      setError('请输入密码');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const session = await iamLogin(username, password);
      saveAuthSession(session);
      onLogin(session.username);
    } catch (err) {
      setError(err instanceof Error ? err.message : '鉴权失败，请重试');
    } finally {
      setBusy(false);
    }
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
            disabled={busy}
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
            disabled={busy}
            onChange={(e) => { setPassword(e.target.value); setError(''); }}
          />

          {error ? <div className="login-error">{error}</div> : null}

          <button type="submit" className="login-submit" disabled={busy}>
            {busy ? '登录中…' : '登录'}
          </button>
          <div className="login-tip">暂无账号？请联系系统管理员</div>
        </form>
      </div>
      <div className="login-right">
        <img src={loginHero} alt="" className="login-hero" />
      </div>
    </div>
  );
}
