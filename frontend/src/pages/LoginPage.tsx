import { useState } from 'react';
import { Cpu, Eye, EyeOff, LogIn } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import ErrorState from '../components/feedback/ErrorState';
import { Button, Card, Input } from '../components/ui';
import { useAuth } from '../store/AuthContext';

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, isLoading } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? '/';

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');

    if (!email || !password) {
      setError('Please enter both email and password.');
      return;
    }

    try {
      await login(email, password);
      toast.success('Login successful.');
      navigate(from, { replace: true });
    } catch (loginError) {
      const message = loginError instanceof Error ? loginError.message : 'Login failed';
      setError(message);
      toast.error(message);
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 px-4 py-10">
      <div className="mx-auto grid max-w-5xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-elevated lg:grid-cols-[1.1fr_1fr]">
        <section className="hidden bg-slate-900 p-10 text-white lg:flex lg:flex-col lg:justify-between">
          <div>
            <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-primary-600">
              <Cpu className="h-6 w-6" />
            </div>
            <h1 className="mt-6 text-3xl font-semibold tracking-tight">AI Interview Platform</h1>
            <p className="mt-3 text-sm text-slate-300">Structured hiring workflows with real-time interview operations and reporting.</p>
          </div>
          <p className="text-xs text-slate-400">Recruiter Console v1.0.0</p>
        </section>

        <section className="p-6 sm:p-10">
          <div className="max-w-md">
            <h2 className="text-2xl font-semibold text-slate-900">Sign in</h2>
            <p className="mt-2 text-sm text-slate-600">Use your recruiter credentials to continue.</p>
          </div>

          <Card className="mt-6 p-6">
            <form onSubmit={handleSubmit} className="space-y-4">
              {error ? <ErrorState title="Authentication failed" message={error} /> : null}

              <Input
                id="email"
                label="Email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="recruiter@company.com"
                autoComplete="email"
              />

              <div className="space-y-2">
                <label htmlFor="password" className="text-sm font-medium text-slate-700">
                  Password
                </label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Enter password"
                    autoComplete="current-password"
                    className="pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((prev) => !prev)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 transition-colors hover:text-slate-700"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              <Button type="submit" className="w-full" isLoading={isLoading}>
                {!isLoading ? <LogIn className="h-4 w-4" /> : null}
                Sign In
              </Button>
            </form>

            <div className="mt-5 space-y-1.5 text-sm text-slate-600">
              <p>
                New recruiter?{' '}
                <Link to="/signup" className="font-medium text-primary-700 hover:text-primary-800">
                  Create account
                </Link>
              </p>
              <p>
                Candidate access?{' '}
                <Link to="/candidate/login" className="font-medium text-primary-700 hover:text-primary-800">
                  Candidate login
                </Link>
              </p>
            </div>
          </Card>
        </section>
      </div>
    </div>
  );
}
