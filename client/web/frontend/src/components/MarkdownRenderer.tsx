/**
 * Markdown 渲染器（react-markdown + GFM）
 */
import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Check, Copy } from 'lucide-react';

function CodeBlock({ className, children }: { className?: string; children?: React.ReactNode }) {
  const [copied, setCopied] = useState(false);
  const text = String(children ?? '').replace(/\n$/, '');

  const handleCopy = () => {
    void navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });
  };

  return (
    <div className="md-code-wrap">
      <pre>
        <code className={className}>{text}</code>
      </pre>
      <button className="md-code-copy" onClick={handleCopy}>
        {copied ? <Check size={11} /> : <Copy size={11} />}
        {copied ? '已复制' : '复制'}
      </button>
    </div>
  );
}

export function MarkdownRenderer({ content }: { content: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre: (props) => <>{props.children}</>,
          code: (props) => {
            const { className, children } = props;
            const isBlock = /language-/.test(className ?? '') || String(children ?? '').includes('\n');
            if (isBlock) {
              return <CodeBlock className={className}>{children}</CodeBlock>;
            }
            return <code className={className}>{children}</code>;
          },
          a: (props) => <a {...props} target="_blank" rel="noreferrer" />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
