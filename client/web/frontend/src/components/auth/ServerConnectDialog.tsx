/**
 * 服务器连接弹窗（第二阶段）
 *
 * 启动后、登录页前展示：输入远端服务器地址（公网 IP / 域名 / localhost / http(s)://...），
 * 点击"连接"后依次测试管理面（:8090）与 jiuwen 后端（:19000）：
 * - 成功：保存到本地 config，关闭弹窗进入登录页
 * - 失败：展示具体错误（哪个服务不可达），允许修改后重试
 * 也可点击"退出程序"直接退出。
 */
import { useState } from 'react';
import { saveServer, testServer } from '../../services/serverConfig';
import './ServerConnectDialog.css';

interface Props {
  initialAddress?: string;
  initialError?: string;
  onConnected: (host: string) => void;
}

function quitApp(): void {
  const quit = window.pywebview?.api?.quit_app;
  if (typeof quit === 'function') {
    void quit();
    return;
  }
  window.close();
}

export function ServerConnectDialog({ initialAddress = '', initialError = '', onConnected }: Props) {
  const [address, setAddress] = useState(initialAddress);
  const [error, setError] = useState(initialError);
  const [testing, setTesting] = useState(false);

  const handleConnect = async (event?: React.FormEvent) => {
    event?.preventDefault();
    const value = address.trim();
    if (!value) {
      setError('请输入服务器地址');
      return;
    }
    setTesting(true);
    setError('');
    try {
      const result = await testServer(value);
      if (!result.ok || !result.host) {
        const details: string[] = [];
        if (result.manager && !result.manager.ok && result.manager.error) details.push(result.manager.error);
        if (result.backend && !result.backend.ok && result.backend.error) details.push(result.backend.error);
        setError(details.length > 0 ? details.join('；') : result.error || '连接失败，请检查服务器地址后重试');
        return;
      }
      await saveServer(value);
      onConnected(result.host);
    } catch (err) {
      setError(err instanceof Error ? err.message : '连接失败，请检查服务器地址后重试');
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="server-connect-mask">
      <form className="server-connect-card" onSubmit={handleConnect}>
        <h2 className="server-connect-title">连接服务器</h2>
        <p className="server-connect-desc">
          请输入远端服务器地址（公网 IP 或域名），客户端将连接管理面（8090）与后端服务（19000）。
        </p>

        <label className="server-connect-label" htmlFor="server-address">服务器地址</label>
        <input
          id="server-address"
          className="server-connect-input"
          placeholder="例如 192.168.1.10 或 http://example.com"
          value={address}
          autoFocus
          disabled={testing}
          onChange={(e) => { setAddress(e.target.value); setError(''); }}
        />

        {error ? <div className="server-connect-error">{error}</div> : null}

        <div className="server-connect-actions">
          <button type="button" className="server-connect-quit" disabled={testing} onClick={quitApp}>
            退出程序
          </button>
          <button type="submit" className="server-connect-submit" disabled={testing}>
            {testing ? <span className="server-connect-spinner" aria-hidden="true" /> : null}
            {testing ? '正在连接…' : '连接'}
          </button>
        </div>
      </form>
    </div>
  );
}
