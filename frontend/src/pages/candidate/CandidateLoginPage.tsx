import { useState } from 'react';
import { ArrowRight, Key, Mail, UserCircle } from 'lucide-react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import ErrorState from '../../components/feedback/ErrorState';
import { Button, Card, Input } from '../../components/ui';

const CANDIDATE_SESSION_KEY = 'candidate_session';

interface CandidateSession {
  sessionToken: string;
  candidateId: string;
  name: string;
  email: string;
  jobTitle: string;
}

export default function CandidateLoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [sessionId, setSessionId] = useState(searchParams.get('session') ?? '');
  const [email, setEmail] = useState(searchParams.get('email') ?? '');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');

    if (!sessionId.trim() || !email.trim()) {
      setError('Please enter both session ID and email.');
      return;
    }

    setIsLoading(true);

    try {
      const response = await fetch('/api/auth/candidate/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId.trim(), email: email.trim() }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Login failed');
      }

      const data = await response.json();

      const session: CandidateSession = {
        sessionToken: data.session_token,
        candidateId: data.candidate_id,
        name: data.name,
        email: data.email,
        jobTitle: data.job_title,
      };
      localStorage.setItem(CANDIDATE_SESSION_KEY, JSON.stringify(session));

      toast.success(`Welcome, ${data.name}`);
      navigate('/candidate/portal');
    } catch (loginError) {
      const message = loginError instanceof Error ? loginError.message : 'Login failed';
      setError(message);
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 px-4 py-10">
      <div className="mx-auto grid max-w-5xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-elevated lg:grid-cols-[1.1fr_1fr]">
        <section className="hidden bg-slate-900 p-10 text-white lg:flex lg:flex-col lg:justify-between">
          <div>
            <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-secondary-600">
              <UserCircle className="h-6 w-6" />
            </div>
            <h1 className="mt-6 text-3xl font-semibold tracking-tight">Candidate Portal</h1>
            <p className="mt-3 text-sm text-slate-300">
              Secure access to your interview session. Use the session ID sent in your invitation email.
            </p>
          </div>
          <p className="text-xs text-slate-400">AI Interview Platform</p>
        </section>

        <section className="p-6 sm:p-10">
          <div className="max-w-md">
            <h2 className="text-2xl font-semibold text-slate-900">Candidate sign in</h2>
            <p className="mt-2 text-sm text-slate-600">Enter your interview session details.</p>
          </div>

          <Card className="mt-6 p-6">
            <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">
              <p className="font-semibold">Need your session ID?</p>
              <p className="mt-1 text-blue-700">Check your interview invitation email from the recruiter.</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              {error ? <ErrorState title="Sign in failed" message={error} /> : null}

              <Input
                id="sessionId"
                label="Session ID"
                type="text"
                value={sessionId}
                onChange={(event) => setSessionId(event.target.value)}
                placeholder="Enter your session ID"
                startIcon={<Key className="h-4 w-4" />}
              />

              <Input
                id="email"
                label="Email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                startIcon={<Mail className="h-4 w-4" />}
              />

              <Button type="submit" className="w-full" isLoading={isLoading}>
                {!isLoading ? <ArrowRight className="h-4 w-4" /> : null}
                Access interview portal
              </Button>
            </form>

            <div className="mt-5 text-sm text-slate-600">
              <p>
                Recruiter account?{' '}
                <Link to="/login" className="font-medium text-primary-700 hover:text-primary-800">
                  Sign in here
                </Link>
              </p>
            </div>
          </Card>
        </section>
      </div>
    </div>
  );
}

export function getCandidateSession(): CandidateSession | null {
  const stored = localStorage.getItem(CANDIDATE_SESSION_KEY);
  if (!stored) return null;
  try {
    return JSON.parse(stored) as CandidateSession;
  } catch {
    return null;
  }
}

export function clearCandidateSession(): void {
  localStorage.removeItem(CANDIDATE_SESSION_KEY);
}
