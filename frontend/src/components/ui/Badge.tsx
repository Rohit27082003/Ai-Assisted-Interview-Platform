import type { PropsWithChildren } from 'react';
import { cn } from '../../utils/cn';

type BadgeVariant = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

interface BadgeProps extends PropsWithChildren {
  variant?: BadgeVariant;
  className?: string;
}

const variantClassMap: Record<BadgeVariant, string> = {
  neutral: 'bg-slate-100 text-slate-700',
  info: 'bg-blue-50 text-blue-700',
  success: 'bg-emerald-50 text-emerald-700',
  warning: 'bg-amber-50 text-amber-700',
  danger: 'bg-rose-50 text-rose-700',
};

export default function Badge({ variant = 'neutral', className, children }: BadgeProps) {
  return (
    <span className={cn('inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold capitalize', variantClassMap[variant], className)}>
      {children}
    </span>
  );
}
