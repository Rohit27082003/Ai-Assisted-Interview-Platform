import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Candidate } from '../../../types';
import EmptyState from '../../../components/feedback/EmptyState';
import { Badge, Button, Card, CardHeader, CardTitle, Table } from '../../../components/ui';
import { CANDIDATE_STATUS_VARIANT, formatCandidateStatus } from '../constants/status';

interface RecentCandidatesTableProps {
  candidates: Candidate[];
}

export default function RecentCandidatesTable({ candidates }: RecentCandidatesTableProps) {
  const navigate = useNavigate();

  const rows = useMemo(() => candidates.slice(0, 5), [candidates]);

  if (rows.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Recent Candidates</CardTitle>
        </CardHeader>
        <EmptyState
          title="No candidates yet"
          description="Candidates will appear here once you add and process resumes for a job description."
          action={<Button onClick={() => navigate('/jd')}>Go to Job Descriptions</Button>}
        />
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent Candidates</CardTitle>
        <Button variant="secondary" onClick={() => navigate('/candidates')}>
          View All
        </Button>
      </CardHeader>
      <Table
        rows={rows}
        getRowKey={(candidate) => candidate.candidate_id}
        columns={[
          {
            key: 'name',
            header: 'Name',
            render: (candidate) => <span className="font-medium text-slate-900">{candidate.name}</span>,
          },
          {
            key: 'email',
            header: 'Email',
            render: (candidate) => candidate.email,
          },
          {
            key: 'score',
            header: 'Resume Match',
            render: (candidate) => `${(candidate.shortlist_score * 100).toFixed(0)}%`,
          },
          {
            key: 'status',
            header: 'Status',
            render: (candidate) => (
              <Badge variant={CANDIDATE_STATUS_VARIANT[candidate.status] ?? 'neutral'}>
                {formatCandidateStatus(candidate.status)}
              </Badge>
            ),
          },
          {
            key: 'actions',
            header: '',
            render: (candidate) => {
              if (['interviewed', 'evaluated', 'reported'].includes(candidate.status) && candidate.interview_id) {
                return (
                  <Button
                    variant="secondary"
                    onClick={() => navigate(`/report/${candidate.interview_id}`)}
                  >
                    View Report
                  </Button>
                );
              }
              return null;
            },
          },
        ]}
      />
    </Card>
  );
}
