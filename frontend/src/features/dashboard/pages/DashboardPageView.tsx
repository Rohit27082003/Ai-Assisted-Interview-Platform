import { BarChart3, FileText, Mic, Users } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import ErrorState from '../../../components/feedback/ErrorState';
import { Loader } from '../../../components/ui';
import RecentCandidatesTable from '../components/RecentCandidatesTable';
import StatCard from '../components/StatCard';
import PipelineFlow from '../components/PipelineFlow';
import { useDashboardData } from '../hooks/useDashboardData';

const statsIconColor = {
  jds: 'bg-blue-600',
  candidates: 'bg-emerald-600',
  shortlisted: 'bg-amber-500',
  interviewed: 'bg-slate-700',
};

export default function DashboardPageView() {
  const navigate = useNavigate();
  const { jds, candidates, isLoading, error, reload } = useDashboardData();

  const stats = [
    {
      label: 'Job Descriptions',
      value: jds.length,
      icon: FileText,
      color: statsIconColor.jds,
      path: '/jd',
    },
    {
      label: 'Total Candidates',
      value: candidates.length,
      icon: Users,
      color: statsIconColor.candidates,
      path: '/candidates',
    },
    {
      label: 'Shortlisted',
      value: candidates.filter((candidate) => ['shortlisted', 'focus_ready'].includes(candidate.status)).length,
      icon: BarChart3,
      color: statsIconColor.shortlisted,
      path: '/candidates',
    },
    {
      label: 'Interviewed',
      value: candidates.filter((candidate) => ['interviewed', 'evaluated', 'reported'].includes(candidate.status)).length,
      icon: Mic,
      color: statsIconColor.interviewed,
      path: '/candidates',
    },
  ];

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Dashboard</h1>
        <p className="text-sm text-slate-600">Operational overview of your hiring workflow and candidate pipeline.</p>
      </header>

      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader label="Loading dashboard" />
        </div>
      ) : null}

      {!isLoading && error ? <ErrorState message={error} onRetry={reload} /> : null}

      {!isLoading && !error ? (
        <>
          <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            {stats.map((stat) => (
              <StatCard
                key={stat.label}
                label={stat.label}
                value={stat.value}
                icon={stat.icon}
                toneClassName={stat.color}
                onClick={() => navigate(stat.path)}
              />
            ))}
          </section>

          <PipelineFlow />

          <RecentCandidatesTable candidates={candidates} />
        </>
      ) : null}
    </div>
  );
}
