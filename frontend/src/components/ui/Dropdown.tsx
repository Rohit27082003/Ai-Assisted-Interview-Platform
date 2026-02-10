import { useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '../../utils/cn';

interface DropdownOption<T extends string = string> {
  label: string;
  value: T;
}

interface DropdownProps<T extends string = string> {
  value: T;
  options: DropdownOption<T>[];
  onChange: (value: T) => void;
  className?: string;
}

export default function Dropdown<T extends string>({ value, options, onChange, className }: DropdownProps<T>) {
  const [open, setOpen] = useState(false);

  const currentLabel = useMemo(
    () => options.find((option) => option.value === value)?.label ?? value,
    [options, value]
  );

  return (
    <div className={cn('relative', className)}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="inline-flex h-10 min-w-40 items-center justify-between gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-700 hover:border-slate-400"
      >
        <span>{currentLabel}</span>
        <ChevronDown className="h-4 w-4" />
      </button>

      {open ? (
        <ul className="absolute z-30 mt-2 w-full rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
          {options.map((option) => (
            <li key={option.value}>
              <button
                type="button"
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
                className={cn(
                  'w-full rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-slate-100',
                  option.value === value ? 'bg-slate-100 text-slate-900' : 'text-slate-600'
                )}
              >
                {option.label}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
