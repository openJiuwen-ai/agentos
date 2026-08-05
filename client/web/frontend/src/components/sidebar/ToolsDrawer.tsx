/**
 * 工具面板抽屉 —— 产出文件(files.list/files.get) + 内存占用(memory.compute)
 * 触发方式仿 jiuwenswarm ToolPanel / OffloadFilesWidget
 */
import { useCallback, useEffect, useState } from 'react';
import { X, FileText, RefreshCw, FolderOpen, MemoryStick } from 'lucide-react';
import { webRequest } from '../../services/webClient';
import './ToolsDrawer.css';

interface OffloadFileListResponse {
  session_id: string;
  files: string[];
  path: string;
  total: number;
}

interface OffloadFileContentResponse {
  filename: string;
  content: string;
}

interface MemoryUsagePayload {
  rss_mb?: number;
  used_percent?: number;
}

function openOffloadDirectory(path: string) {
  const api = (window as unknown as { pywebview?: { api?: { open_path?: (p: string) => Promise<unknown> } } }).pywebview?.api;
  if (api?.open_path && path) {
    void api.open_path(path);
  }
}

export function ToolsDrawer({
  sessionId,
  onClose,
}: {
  sessionId: string | null;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<'files' | 'memory'>('files');
  const [files, setFiles] = useState<string[]>([]);
  const [offloadPath, setOffloadPath] = useState('');
  const [filesLoading, setFilesLoading] = useState(false);
  const [preview, setPreview] = useState<{ filename: string; content: string } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [memory, setMemory] = useState<MemoryUsagePayload | null>(null);

  const sessionReady = Boolean(sessionId && sessionId !== 'new');

  const loadFiles = useCallback(async () => {
    if (!sessionReady || !sessionId) return;
    setFilesLoading(true);
    try {
      const data = await webRequest<OffloadFileListResponse>('files.list', { session_id: sessionId });
      setFiles(data.files || []);
      setOffloadPath(data.path || '');
    } catch {
      setFiles([]);
    } finally {
      setFilesLoading(false);
    }
  }, [sessionId, sessionReady]);

  const loadMemory = useCallback(async () => {
    try {
      const payload = await webRequest<MemoryUsagePayload>('memory.compute');
      setMemory(payload);
    } catch {
      setMemory(null);
    }
  }, []);

  useEffect(() => {
    if (tab === 'files') void loadFiles();
    if (tab === 'memory') void loadMemory();
  }, [tab, loadFiles, loadMemory]);

  const handlePreview = async (filename: string) => {
    if (!sessionId) return;
    setPreviewLoading(true);
    setPreview({ filename, content: '' });
    try {
      const data = await webRequest<OffloadFileContentResponse>('files.get', {
        session_id: sessionId,
        filename,
      });
      setPreview({ filename, content: data.content || '' });
    } catch {
      setPreview({ filename, content: '（内容加载失败）' });
    } finally {
      setPreviewLoading(false);
    }
  };

  return (
    <div className="drawer-mask" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <span className="drawer-title">工具面板</span>
          <button className="icon-btn icon-btn--sm" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="drawer-tabs">
          <button className={`drawer-tab ${tab === 'files' ? 'is-active' : ''}`} onClick={() => setTab('files')}>
            <FileText size={14} /> 产出文件
          </button>
          <button className={`drawer-tab ${tab === 'memory' ? 'is-active' : ''}`} onClick={() => setTab('memory')}>
            <MemoryStick size={14} /> 内存占用
          </button>
        </div>

        <div className="drawer-body">
          {tab === 'files' ? (
            <>
              <div className="drawer-section-head">
                <span className="drawer-section-title">当前会话产出</span>
                <div style={{ display: 'flex', gap: 4 }}>
                  {offloadPath ? (
                    <button className="icon-btn icon-btn--sm" title="打开所在目录" onClick={() => openOffloadDirectory(offloadPath)}>
                      <FolderOpen size={14} />
                    </button>
                  ) : null}
                  <button className="icon-btn icon-btn--sm" title="刷新" onClick={() => void loadFiles()}>
                    <RefreshCw size={14} className={filesLoading ? 'spin' : ''} />
                  </button>
                </div>
              </div>
              {!sessionReady ? (
                <div className="empty-hint">进入会话后可查看产出文件</div>
              ) : files.length === 0 && !filesLoading ? (
                <div className="empty-hint">暂无产出文件</div>
              ) : (
                <div className="drawer-file-list">
                  {files.map((filename) => (
                    <button key={filename} className="drawer-file-item" onClick={() => void handlePreview(filename)}>
                      <FileText size={14} />
                      <span>{filename}</span>
                    </button>
                  ))}
                </div>
              )}
            </>
          ) : (
            <>
              <div className="drawer-section-head">
                <span className="drawer-section-title">后端进程内存</span>
                <button className="icon-btn icon-btn--sm" title="刷新" onClick={() => void loadMemory()}>
                  <RefreshCw size={14} />
                </button>
              </div>
              {memory ? (
                <div className="memory-cards">
                  <div className="memory-card">
                    <div className="memory-value">{typeof memory.rss_mb === 'number' ? memory.rss_mb.toFixed(1) : '--'}</div>
                    <div className="memory-label">RSS (MB)</div>
                  </div>
                  <div className="memory-card">
                    <div className="memory-value">{typeof memory.used_percent === 'number' ? memory.used_percent.toFixed(1) : '--'}</div>
                    <div className="memory-label">已用 (%)</div>
                  </div>
                </div>
              ) : (
                <div className="empty-hint">未获取到数据</div>
              )}
            </>
          )}
        </div>
      </div>

      {/* 文件预览 */}
      {preview ? (
        <div className="modal-mask" onClick={() => setPreview(null)}>
          <div className="modal-card drawer-preview" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div className="modal-title">{preview.filename}</div>
              <button className="icon-btn icon-btn--sm" onClick={() => setPreview(null)}><X size={16} /></button>
            </div>
            <div className="modal-body">
              {previewLoading ? <div className="empty-hint">加载中…</div> : (
                <pre className="drawer-preview-content">{preview.content || '（空文件）'}</pre>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
