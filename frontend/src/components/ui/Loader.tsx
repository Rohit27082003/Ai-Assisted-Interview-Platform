import { cn } from '../../utils/cn';

interface LoaderProps {
  className?: string;
  label?: string;
}

export default function Loader({ className, label = 'Loading' }: LoaderProps) {
  return (
    <div className={cn('inline-flex items-center gap-2 text-slate-500', className)} role="status" aria-live="polite">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-r-primary-600" aria-hidden="true" />
      <span className="text-sm">{label}</span>
    </div>
  );
}
