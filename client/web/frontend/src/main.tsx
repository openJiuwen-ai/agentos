import './i18n';
import ReactDOM from 'react-dom/client';
import App from './App.tsx';
import './styles/foundation.css';
import './styles/themes/default/light.css';
import './styles/global.css';

// 全局禁止 <img> 拖拽 —— 防止拖入输入框时产生 URL 地址
document.addEventListener('dragstart', e => {
  if (e.target instanceof HTMLImageElement) e.preventDefault();
});

ReactDOM.createRoot(document.getElementById('root')!).render(<App />);
