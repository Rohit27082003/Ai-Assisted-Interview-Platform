import { forwardRef, type InputHTMLAttributes, type ReactNode } from 'react';
import { cn } from '../../utils/cn';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
  startIcon?: ReactNode;
  endAdornment?: ReactNode;
}

const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, label, hint, error, id, startIcon, endAdornment, ...props },
  ref
) {
  const inputId = id ?? props.name;

  return (
    <label className="flex w-full flex-col gap-2" htmlFor={inputId}>
      {label ? <span className="text-sm font-medium text-slate-700">{label}</span> : null}
      <div className="relative">
        {startIcon ? (
          <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-400">
            {startIcon}
          </span>
        ) : null}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            'h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900',
            'outline-none transition-colors duration-150 placeholder:text-slate-400',
            'focus:border-primary-500 focus:ring-2 focus:ring-primary-100',
            startIcon ? 'pl-9' : '',
            endAdornment ? 'pr-10' : '',
            error ? 'border-red-400 focus:border-red-500 focus:ring-red-100' : '',
            className
          )}
          {...props}
        />
        {endAdornment ? (
          <span className="absolute inset-y-0 right-3 flex items-center">{endAdornment}</span>
        ) : null}
      </div>
      {error ? <span className="text-xs text-red-600">{error}</span> : null}
      {!error && hint ? <span className="text-xs text-slate-500">{hint}</span> : null}
    </label>
  );
});

export default Input;
