/**
 * 通用弹出层：锚点定位 + 点击外部关闭 + Esc 关闭
 */
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';

export type PopupPlacement = 'bottom-start' | 'bottom-end' | 'top-start' | 'top-end' | 'right-start';

interface PopupProps {
  open: boolean;
  anchorRef: React.RefObject<HTMLElement | null>;
  placement?: PopupPlacement;
  offset?: number;
  onClose: () => void;
  children: ReactNode;
  className?: string;
}

export function Popup({ open, anchorRef, placement = 'bottom-start', offset = 6, onClose, children, className }: PopupProps) {
  const popRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);

  useLayoutEffect(() => {
    if (!open) return;
    const anchor = anchorRef.current;
    const pop = popRef.current;
    if (!anchor || !pop) return;
    const rect = anchor.getBoundingClientRect();
    const popRect = pop.getBoundingClientRect();
    let left = rect.left;
    let top = rect.bottom + offset;
    switch (placement) {
      case 'bottom-end':
        left = rect.right - popRect.width;
        top = rect.bottom + offset;
        break;
      case 'top-start':
        left = rect.left;
        top = rect.top - popRect.height - offset;
        break;
      case 'top-end':
        left = rect.right - popRect.width;
        top = rect.top - popRect.height - offset;
        break;
      case 'right-start':
        left = rect.right + offset;
        top = rect.top;
        break;
      default:
        break;
    }
    // 视口边界保护
    left = Math.max(8, Math.min(left, window.innerWidth - popRect.width - 8));
    top = Math.max(8, Math.min(top, window.innerHeight - popRect.height - 8));
    setPos({ left, top });
  }, [open, anchorRef, placement, offset]);

  useEffect(() => {
    if (!open) return;
    const handleDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (popRef.current?.contains(target)) return;
      if (anchorRef.current?.contains(target)) return;
      onClose();
    };
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', handleDown, true);
    document.addEventListener('keydown', handleKey);
    window.addEventListener('resize', onClose);
    return () => {
      document.removeEventListener('mousedown', handleDown, true);
      document.removeEventListener('keydown', handleKey);
      window.removeEventListener('resize', onClose);
    };
  }, [open, onClose, anchorRef]);

  if (!open) return null;
  return (
    <div
      ref={popRef}
      className={`fade-in ${className ?? ''}`}
      style={{
        position: 'fixed',
        left: pos?.left ?? -9999,
        top: pos?.top ?? -9999,
        zIndex: 1500,
        visibility: pos ? 'visible' : 'hidden',
      }}
    >
      {children}
    </div>
  );
}
