import type { PropsWithChildren } from 'react';
import { cn } from '../../utils/cn';

interface ModalProps extends PropsWithChildren {
  open: boolean;
  onClose: () => void;
  title?: string;
  className?: string;
}

export default function Modal({ open, onClose, title, className, children }: ModalProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4" role="dialog" aria-modal="true">
      <div className={cn('w-full max-w-lg rounded-xl border border-slate-200 bg-white p-6 shadow-lg', className)}>
        <div className="mb-4 flex items-center justify-between gap-4">
          {title ? <h3 className="text-lg font-semibold text-slate-900">{title}</h3> : <span />}
          <button
            onClick={onClose}
            className="rounded-md p-1 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
            aria-label="Close modal"
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
