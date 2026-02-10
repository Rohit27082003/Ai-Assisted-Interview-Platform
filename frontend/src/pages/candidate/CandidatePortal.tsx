import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, Clock, CheckCircle, XCircle, Briefcase, User, LogOut } from 'lucide-react';
import toast from 'react-hot-toast';
import { Button, Card, Badge, Loader } from '../../components/ui';
import { clearCandidateSession, getCandidateSession } from './CandidateLoginPage';

interface PortalInfo {
  candidate_id: string;
  name: string;
  email: string;
  job_title: string;
  interview_status: string | null;
  interview_id: string | null;
  can_start_interview: boolean;
  instructions: string;
}

export default function CandidatePortal() {
  const navigate = useNavigate();
  const [portalInfo, setPortalInfo] = useState<PortalInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [startingInterview, setStartingInterview] = useState(false);

  useEffect(() => {
    loadPortalInfo();
  }, []);

  const loadPortalInfo = async () => {
    const session = getCandidateSession();
    if (!session) {
      toast.error('Session expired. Please login again.');
      navigate('/candidate/login');
      return;
    }

    try {
      const response = await fetch('/api/candidate-portal/info', {
        headers: {
          'X-Candidate-Session': session.sessionToken,
        },
      });

      if (!response.ok) {
        if (response.status === 401) {
          clearCandidateSession();
          toast.error('Session expired. Please login again.');
          navigate('/candidate/login');
          return;
        }
        throw new Error('Failed to load portal info');
      }

      const data = await response.json();
      setPortalInfo(data);
    } catch {
      toast.error('Failed to load portal information');
    } finally {
      setLoading(false);
    }
  };

  const handleStartInterview = async () => {
    const session = getCandidateSession();
    if (!session) return;

    setStartingInterview(true);
    try {
      const response = await fetch('/api/candidate-portal/start-interview', {
        method: 'POST',
        headers: {
          'X-Candidate-Session': session.sessionToken,
        },
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to start interview');
      }

      const data = await response.json();
      toast.success('Interview started');
      navigate(`/candidate/interview/${data.interview_id}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to start interview';
      toast.error(message);
    } finally {
      setStartingInterview(false);
    }
  };

  const handleLogout = () => {
    clearCandidateSession();
    toast.success('Logged out successfully');
    navigate('/candidate/login');
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100">
        <Loader label="Loading portal" />
      </div>
    );
  }

  if (!portalInfo) {
    return null;
  }

  const getStatusBadgeVariant = () => {
    switch (portalInfo.interview_status) {
      case 'completed':
        return 'success' as const;
      case 'in_progress':
        return 'warning' as const;
      case 'terminated':
        return 'danger' as const;
      default:
        return 'neutral' as const;
    }
  };

  const getStatusIcon = () => {
    switch (portalInfo.interview_status) {
      case 'completed':
        return <CheckCircle className="h-4 w-4" />;
      case 'in_progress':
        return <Clock className="h-4 w-4" />;
      case 'terminated':
        return <XCircle className="h-4 w-4" />;
      default:
        return <Clock className="h-4 w-4" />;
    }
  };

  const getStatusText = () => {
    switch (portalInfo.interview_status) {
      case 'completed':
        return 'Completed';
      case 'in_progress':
        return 'In Progress';
      case 'pending':
        return 'Ready to Start';
      case 'terminated':
        return 'Terminated';
      default:
        return 'Not Started';
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 px-4 py-8">
      <div className="mx-auto max-w-4xl space-y-4">
        <Card>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-semibold text-slate-900">Candidate Portal</h1>
              <p className="mt-1 text-sm text-slate-600">Manage your interview session and review instructions.</p>
            </div>
            <Button variant="secondary" onClick={handleLogout}>
              <LogOut className="h-4 w-4" />
              Logout
            </Button>
          </div>
        </Card>

        <Card>
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary-100 text-primary-700">
              <User className="h-6 w-6" />
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="truncate text-xl font-semibold text-slate-900">{portalInfo.name}</h2>
              <p className="truncate text-sm text-slate-600">{portalInfo.email}</p>
            </div>
          </div>

          <div className="mt-4 border-t border-slate-200 pt-4">
            <div className="flex items-center gap-2 text-sm text-slate-700">
              <Briefcase className="h-4 w-4 text-slate-500" />
              <span>Position:</span>
              <span className="font-semibold text-slate-900">{portalInfo.job_title}</span>
            </div>
          </div>
        </Card>

        <Card>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h3 className="text-lg font-semibold text-slate-900">Interview Status</h3>
            <Badge variant={getStatusBadgeVariant()} className="gap-1.5">
              {getStatusIcon()}
              {getStatusText()}
            </Badge>
          </div>

          <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm whitespace-pre-line text-slate-700">
            {portalInfo.instructions}
          </div>

          {portalInfo.can_start_interview ? (
            <div className="mt-5">
              <Button onClick={handleStartInterview} isLoading={startingInterview} className="w-full sm:w-auto">
                {!startingInterview ? <Play className="h-4 w-4" /> : null}
                Start Interview
              </Button>
            </div>
          ) : null}

          {portalInfo.interview_status === 'in_progress' && portalInfo.interview_id ? (
            <div className="mt-3">
              <Button
                variant="secondary"
                onClick={() => navigate(`/candidate/interview/${portalInfo.interview_id}`)}
                className="w-full sm:w-auto"
              >
                <Play className="h-4 w-4" />
                Continue Interview
              </Button>
            </div>
          ) : null}
        </Card>

        <Card className="border-blue-200 bg-blue-50">
          <h3 className="text-base font-semibold text-blue-900">Tips for success</h3>
          <ul className="mt-3 space-y-1.5 text-sm text-blue-800">
            <li>Use a quiet environment with stable internet.</li>
            <li>Confirm microphone permission before starting.</li>
            <li>Read each question fully before answering.</li>
            <li>Speak clearly at a steady pace.</li>
            <li>Avoid tab switching during interview time.</li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
