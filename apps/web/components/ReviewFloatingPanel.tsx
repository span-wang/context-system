"use client";

import { PointerEvent, ReactNode, useEffect, useRef, useState } from "react";
import { Grip, X } from "lucide-react";

type PanelPosition = {
  x: number;
  y: number;
};

type ReviewFloatingPanelProps = {
  title: string;
  subtitle?: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
};

const defaultPosition: PanelPosition = { x: 48, y: 96 };

export default function ReviewFloatingPanel({
  title,
  subtitle,
  open,
  onClose,
  children,
  footer,
}: ReviewFloatingPanelProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);
  const [position, setPosition] = useState<PanelPosition>(defaultPosition);

  useEffect(() => {
    setPosition((current) => {
      const panel = panelRef.current;
      const width = panel?.offsetWidth || 440;
      const height = panel?.offsetHeight || 560;
      const maxX = Math.max(12, window.innerWidth - width - 12);
      const maxY = Math.max(12, window.innerHeight - height - 12);
      return {
        x: Math.min(current.x, maxX),
        y: Math.min(current.y, maxY),
      };
    });
  }, [open]);

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: position.x,
      originY: position.y,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!dragRef.current || dragRef.current.pointerId !== event.pointerId) return;
    const nextX = dragRef.current.originX + (event.clientX - dragRef.current.startX);
    const nextY = dragRef.current.originY + (event.clientY - dragRef.current.startY);
    const panel = panelRef.current;
    const width = panel?.offsetWidth || 480;
    const height = panel?.offsetHeight || 640;
    setPosition({
      x: clamp(nextX, 16, Math.max(16, window.innerWidth - width - 16)),
      y: clamp(nextY, 16, Math.max(16, window.innerHeight - height - 16)),
    });
  }

  function endPointerDrag(event: PointerEvent<HTMLDivElement>) {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  return (
    <div
      aria-hidden={!open}
      className="floatingReviewRoot"
      data-open={open ? "true" : "false"}
      role="dialog"
      aria-modal="false"
      aria-label={title}
    >
      <div
        className="floatingReviewPanel"
        ref={panelRef}
        style={{ left: position.x, top: position.y }}
      >
        <div
          className="floatingReviewHeader"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endPointerDrag}
          onPointerCancel={endPointerDrag}
        >
          <div className="floatingReviewTitle">
            <span className="dragHandle" aria-hidden="true">
              <Grip size={16} />
            </span>
            <div>
              <strong>{title}</strong>
              {subtitle ? <span>{subtitle}</span> : null}
            </div>
          </div>
          <button className="button" type="button" onClick={onClose} aria-label="关闭审查弹窗">
            <X size={16} />
          </button>
        </div>
        <div className="floatingReviewBody">{children}</div>
        {footer ? <div className="floatingReviewFooter">{footer}</div> : null}
      </div>
    </div>
  );
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}
