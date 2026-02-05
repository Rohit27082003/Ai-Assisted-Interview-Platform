import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileText, Users, Mic, BarChart3, ArrowRight } from 'lucide-react';
import { jdApi, candidateApi } from '../services/api';
import type { JobDescription, Candidate } from '../types';

export default function DashboardPage() {
  const navigate = useNavigate();
  const [jds, setJDs] = useState<JobDescription[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [jdList, candidateList] = await Promise.all([
        jdApi.list(),
        candidateApi.list(),
      ]);
      setJDs(jdList);
      setCandidates(candidateList);
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
    } finally {
      setLoading(false);
    }
  };

  const stats = [
    {
      label: 'Job Descriptions',
      value: jds.length,
      icon: FileText,
      color: 'bg-blue-500',
      path: '/jd',
    },
    {
      label: 'Total Candidates',
      value: candidates.length,
      icon: Users,
      color: 'bg-green-500',
      path: '/candidates',
    },
    {
      label: 'Shortlisted',
      value: candidates.filter((c) => c.status === 'shortlisted' || c.status === 'focus_ready').length,
      icon: BarChart3,
      color: 'bg-yellow-500',
      path: '/candidates',
    },
    {
      label: 'Interviewed',
      value: candidates.filter((c) =>
        ['interviewed', 'evaluated', 'reported'].includes(c.status)
      ).length,
      icon: Mic,
      color: 'bg-purple-500',
      path: '/candidates',
    },
  ];

  const statusColorMap: Record<string, string> = {
    uploaded: 'badge-gray',
    parsed: 'badge-blue',
    shortlisted: 'badge-green',
    rejected: 'badge-red',
    focus_ready: 'badge-yellow',
    interviewing: 'badge-blue',
    interviewed: 'badge-green',
    evaluated: 'badge-green',
    reported: 'badge-green',
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
        <p className="mt-2 text-gray-600">
          AI Interview Orchestrator — Overview of your hiring pipeline
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {stats.map(({ label, value, icon: Icon, color, path }) => (
          <div
            key={label}
            className="card cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => navigate(path)}
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">{label}</p>
                <p className="text-3xl font-bold mt-1">{value}</p>
              </div>
              <div className={`${color} p-3 rounded-lg`}>
                <Icon className="w-6 h-6 text-white" />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Pipeline Flow */}
      <div className="card">
        <h2 className="text-lg font-semibold mb-4">Pipeline Architecture</h2>
        <div className="flex items-center gap-2 overflow-x-auto py-4">
          {[
            'JD Intelligence',
            'Resume Parsing',
            'Shortlisting',
            'Focus Areas',
            'Interview',
            'Evaluation',
            'Report',
          ].map((stage, i) => (
            <div key={stage} className="flex items-center gap-2">
              <div className="bg-primary-50 text-primary-700 px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap">
                {stage}
              </div>
              {i < 6 && <ArrowRight className="w-4 h-4 text-gray-400 flex-shrink-0" />}
            </div>
          ))}
        </div>
      </div>

      {/* Recent Candidates */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Recent Candidates</h2>
          <button className="btn-primary text-sm" onClick={() => navigate('/candidates')}>
            View All
          </button>
        </div>
        {candidates.length === 0 ? (
          <p className="text-gray-500 py-8 text-center">
            No candidates yet. Start by creating a Job Description.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-sm text-gray-500 border-b">
                  <th className="pb-3 font-medium">Name</th>
                  <th className="pb-3 font-medium">Email</th>
                  <th className="pb-3 font-medium">Score</th>
                  <th className="pb-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {candidates.slice(0, 5).map((c) => (
                  <tr key={c.candidate_id} className="border-b last:border-0">
                    <td className="py-3 font-medium">{c.name}</td>
                    <td className="py-3 text-gray-600">{c.email}</td>
                    <td className="py-3">{(c.shortlist_score * 100).toFixed(0)}%</td>
                    <td className="py-3">
                      <span className={statusColorMap[c.status] || 'badge-gray'}>
                        {c.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
