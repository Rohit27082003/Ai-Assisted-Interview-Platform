import { useState, useEffect } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { Mail, Key, ArrowRight, RefreshCw, CheckCircle } from 'lucide-react';
import toast from 'react-hot-toast';

export default function ConfirmSignupPage() {
    const navigate = useNavigate();
    const location = useLocation();
    const [email, setEmail] = useState('');
    const [code, setCode] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [isResending, setIsResending] = useState(false);
    const [error, setError] = useState('');

    // Get email from location state (passed from signup)
    useEffect(() => {
        console.log('Location State:', location.state); // DEBUG: Check if email is passed
        const stateEmail = (location.state as { email?: string })?.email;
        if (stateEmail) {
            setEmail(stateEmail);
        }
    }, [location.state]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        if (!email.trim() || !code.trim()) {
            setError('Please enter your email and confirmation code');
            return;
        }

        setIsLoading(true);

        try {
            const response = await fetch('/api/auth/confirm-signup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: email.trim(),
                    confirmation_code: code.trim()
                }),
            });

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || 'Confirmation failed');
            }

            toast.success('Account confirmed! You can now log in.');
            navigate('/login', { state: { email } });
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Confirmation failed';
            setError(message);
            toast.error(message);
        } finally {
            setIsLoading(false);
        }
    };

    const handleResendCode = async () => {
        if (!email.trim()) {
            setError('Please enter your email address');
            return;
        }

        setIsResending(true);
        setError('');

        try {
            const response = await fetch('/api/auth/resend-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: email.trim() }),
            });

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || 'Failed to resend code');
            }

            toast.success('Confirmation code sent! Check your email.');
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Failed to resend code';
            setError(message);
            toast.error(message);
        } finally {
            setIsResending(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 py-12 px-4">
            <div className="max-w-md w-full space-y-8">
                {/* Header */}
                <div className="text-center">
                    <div className="flex justify-center mb-4">
                        <div className="w-16 h-16 bg-gradient-to-br from-green-500 to-emerald-600 rounded-2xl flex items-center justify-center shadow-lg">
                            <CheckCircle className="w-9 h-9 text-white" />
                        </div>
                    </div>
                    <h2 className="text-3xl font-bold text-white">Confirm Your Account</h2>
                    <p className="mt-2 text-gray-400">Enter the confirmation code sent to your email</p>
                </div>

                {/* Confirmation Form */}
                <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8 shadow-2xl border border-white/20">
                    <form onSubmit={handleSubmit} className="space-y-5">
                        {error && (
                            <div className="bg-red-500/20 border border-red-500/50 text-red-200 px-4 py-3 rounded-lg text-sm">
                                {error}
                            </div>
                        )}

                        <div>
                            <label htmlFor="email" className="block text-sm font-medium text-gray-200 mb-2">
                                Email Address
                            </label>
                            <div className="relative">
                                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                                <input
                                    id="email"
                                    type="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    placeholder="recruiter@company.com"
                                    className="w-full pl-11 pr-4 py-3 bg-white/5 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition"
                                    autoComplete="email"
                                />
                            </div>
                        </div>

                        <div>
                            <label htmlFor="code" className="block text-sm font-medium text-gray-200 mb-2">
                                Confirmation Code
                            </label>
                            <div className="relative">
                                <Key className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                                <input
                                    id="code"
                                    type="text"
                                    value={code}
                                    onChange={(e) => setCode(e.target.value)}
                                    placeholder="123456"
                                    className="w-full pl-11 pr-4 py-3 bg-white/5 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition tracking-widest text-center text-lg"
                                    maxLength={6}
                                    autoComplete="one-time-code"
                                />
                            </div>
                            <p className="mt-1 text-xs text-gray-500">Check your email for a 6-digit code</p>
                        </div>

                        <button
                            type="submit"
                            disabled={isLoading}
                            className="w-full py-3 px-4 bg-gradient-to-r from-green-500 to-emerald-600 text-white font-semibold rounded-lg shadow-lg hover:from-green-600 hover:to-emerald-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 focus:ring-offset-slate-900 transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                        >
                            {isLoading ? (
                                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white" />
                            ) : (
                                <>
                                    Confirm Account
                                    <ArrowRight className="w-5 h-5" />
                                </>
                            )}
                        </button>
                    </form>

                    <div className="mt-6 flex flex-col items-center gap-3">
                        <button
                            onClick={handleResendCode}
                            disabled={isResending}
                            className="text-purple-400 hover:text-purple-300 transition text-sm flex items-center gap-2 disabled:opacity-50"
                        >
                            {isResending ? (
                                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-purple-400" />
                            ) : (
                                <RefreshCw className="w-4 h-4" />
                            )}
                            Resend confirmation code
                        </button>

                        <p className="text-sm text-gray-400">
                            Already confirmed?{' '}
                            <Link to="/login" className="text-purple-400 hover:text-purple-300 transition">
                                Sign in
                            </Link>
                        </p>
                    </div>
                </div>

                {/* Footer */}
                <p className="text-center text-gray-500 text-sm">
                    Powered by AI Interview Orchestrator
                </p>
            </div>
        </div>
    );
}
