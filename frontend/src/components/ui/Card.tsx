import type { PropsWithChildren } from 'react';
import { cn } from '../../utils/cn';

interface CardProps extends PropsWithChildren {
  className?: string;
}

export function Card({ className, children }: CardProps) {
  return <section className={cn('rounded-xl border border-slate-200 bg-white p-6 shadow-sm', className)}>{children}</section>;
}

interface CardSectionProps extends PropsWithChildren {
  className?: string;
}

export function CardHeader({ className, children }: CardSectionProps) {
  return <header className={cn('mb-4 flex items-start justify-between gap-4', className)}>{children}</header>;
}

export function CardTitle({ className, children }: CardSectionProps) {
  return <h2 className={cn('text-lg font-semibold tracking-tight text-slate-900', className)}>{children}</h2>;
}

export function CardDescription({ className, children }: CardSectionProps) {
  return <p className={cn('text-sm text-slate-600', className)}>{children}</p>;
}
