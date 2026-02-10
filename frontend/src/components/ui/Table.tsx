import type { ReactNode } from 'react';
import { cn } from '../../utils/cn';

interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  className?: string;
}

interface TableProps<T> {
  columns: Column<T>[];
  rows: T[];
  getRowKey: (row: T) => string;
  className?: string;
}

export default function Table<T>({ columns, rows, getRowKey, className }: TableProps<T>) {
  return (
    <div className={cn('overflow-x-auto', className)}>
      <table className="min-w-full border-separate border-spacing-0">
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                className={cn('border-b border-slate-200 px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500', column.className)}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={getRowKey(row)} className="hover:bg-slate-50">
              {columns.map((column) => (
                <td key={column.key} className={cn('border-b border-slate-100 px-4 py-3 text-sm text-slate-700', column.className)}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
