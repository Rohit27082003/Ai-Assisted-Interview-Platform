import { useState } from 'react';
import { ArrowRight, Briefcase, Eye, EyeOff, Lock, Mail, Phone, User } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import ErrorState from '../components/feedback/ErrorState';
import { Button, Card, Input } from '../components/ui';

export default function SignupPage() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');

    if (!name.trim() || !email.trim() || !password || !phoneNumber.trim()) {
      setError('Please fill in all fields.');
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }

    const phoneRegex = /^\+[1-9]\d{1,14}$/;
    if (!phoneRegex.test(phoneNumber)) {
      setError('Phone number must be in international format (e.g., +1234567890).');
      return;
    }

    setIsLoading(true);

    try {
      const response = await fetch('/api/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: email.trim(),
          password,
          name: name.trim(),
          phone_number: phoneNumber.trim(),
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Signup failed');
      }

      const data = await response.json();

      if (data.requires_confirmation) {
        toast.success('Account created. Check your email for the confirmation code.');
        navigate('/confirm-signup', { state: { email } });
      } else {
        toast.success('Account created successfully.');
        navigate('/login');
      }
    } catch (signupError) {
      const message = signupError instanceof Error ? signupError.message : 'Signup failed';
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
            <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-primary-600">
              <Briefcase className="h-6 w-6" />
            </div>
            <h1 className="mt-6 text-3xl font-semibold tracking-tight">Create recruiter account</h1>
            <p className="mt-3 text-sm text-slate-300">
              Set up your account to manage job descriptions, candidate pipelines, interviews, and reports.
            </p>
          </div>
          <p className="text-xs text-slate-400">AI Interview Platform</p>
        </section>

        <section className="p-6 sm:p-10">
          <div className="max-w-md">
            <h2 className="text-2xl font-semibold text-slate-900">Sign up</h2>
            <p className="mt-2 text-sm text-slate-600">Create your recruiter account to continue.</p>
          </div>

          <Card className="mt-6 p-6">
            <form onSubmit={handleSubmit} className="space-y-4">
              {error ? <ErrorState title="Signup failed" message={error} /> : null}

              <Input
                id="name"
                label="Full Name"
                type="text"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="John Doe"
                autoComplete="name"
                startIcon={<User className="h-4 w-4" />}
              />

              <Input
                id="email"
                label="Email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="recruiter@company.com"
                autoComplete="email"
                startIcon={<Mail className="h-4 w-4" />}
              />

              <Input
                id="phone"
                label="Phone Number"
                type="tel"
                value={phoneNumber}
                onChange={(event) => setPhoneNumber(event.target.value)}
                placeholder="+1234567890"
                autoComplete="tel"
                hint="Use international format (for example: +1234567890)."
                startIcon={<Phone className="h-4 w-4" />}
              />

              <Input
                id="password"
                label="Password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Enter password"
                autoComplete="new-password"
                hint="Minimum 8 characters."
                startIcon={<Lock className="h-4 w-4" />}
                endAdornment={
                  <button
                    type="button"
                    onClick={() => setShowPassword((prev) => !prev)}
                    className="text-slate-400 transition-colors hover:text-slate-700"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                }
              />

              <Input
                id="confirmPassword"
                label="Confirm Password"
                type={showPassword ? 'text' : 'password'}
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                placeholder="Re-enter password"
                autoComplete="new-password"
                startIcon={<Lock className="h-4 w-4" />}
              />

              <Button type="submit" className="w-full" isLoading={isLoading}>
                {!isLoading ? <ArrowRight className="h-4 w-4" /> : null}
                Create Account
              </Button>
            </form>

            <div className="mt-5 text-sm text-slate-600">
              <p>
                Already have an account?{' '}
                <Link to="/login" className="font-medium text-primary-700 hover:text-primary-800">
                  Sign in
                </Link>
              </p>
            </div>
          </Card>
        </section>
      </div>
    </div>
  );
}
