import type { LucideIcon } from 'lucide-react';
import { Card } from '../../../components/ui';

interface StatCardProps {
  label: string;
  value: number;
  icon: LucideIcon;
  toneClassName: string;
  onClick: () => void;
}

export default function StatCard({ label, value, icon: Icon, toneClassName, onClick }: StatCardProps) {
  return (
    <button type="button" className="w-full text-left" onClick={onClick}>
      <Card className="h-full transition-all hover:-translate-y-0.5 hover:shadow-elevated">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm text-slate-500">{label}</p>
            <p className="mt-1 text-3xl font-semibold text-slate-900">{value}</p>
          </div>
          <div className={`flex h-11 w-11 items-center justify-center rounded-lg ${toneClassName}`}>
            <Icon className="h-5 w-5 text-white" />
          </div>
        </div>
      </Card>
    </button>
  );
}
