import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Key, Mail, ArrowRight, UserCircle } from 'lucide-react';
import toast from 'react-hot-toast';

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

    // Pre-fill from URL params if provided
    const [sessionId, setSessionId] = useState(searchParams.get('session') || '');
    const [email, setEmail] = useState(searchParams.get('email') || '');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        if (!sessionId.trim() || !email.trim()) {
            setError('Please enter both session ID and email');
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

            // Store session
            const session: CandidateSession = {
                sessionToken: data.session_token,
                candidateId: data.candidate_id,
                name: data.name,
                email: data.email,
                jobTitle: data.job_title,
            };
            localStorage.setItem(CANDIDATE_SESSION_KEY, JSON.stringify(session));

            toast.success(`Welcome, ${data.name}!`);
            navigate('/candidate/portal');
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Login failed';
            setError(message);
            toast.error(message);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-emerald-900 via-teal-900 to-slate-900 py-12 px-4">
            <div className="max-w-md w-full space-y-8">
                {/* Header */}
                <div className="text-center">
                    <div className="flex justify-center mb-4">
                        <div className="w-16 h-16 bg-gradient-to-br from-emerald-500 to-teal-600 rounded-2xl flex items-center justify-center shadow-lg">
                            <UserCircle className="w-9 h-9 text-white" />
                        </div>
                    </div>
                    <h2 className="text-3xl font-bold text-white">Candidate Portal</h2>
                    <p className="mt-2 text-gray-400">Enter your interview session details</p>
                </div>

                {/* Login Form */}
                <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8 shadow-2xl border border-white/20">
                    <form onSubmit={handleSubmit} className="space-y-6">
                        {error && (
                            <div className="bg-red-500/20 border border-red-500/50 text-red-200 px-4 py-3 rounded-lg text-sm">
                                {error}
                            </div>
                        )}

                        <div className="bg-teal-500/10 border border-teal-500/30 text-teal-200 px-4 py-3 rounded-lg text-sm">
                            <p className="font-medium">Need a session ID?</p>
                            <p className="mt-1 text-teal-300/80">
                                Your session ID was sent by the recruiter. Check your email for the interview invitation.
                            </p>
                        </div>

                        <div>
                            <label htmlFor="sessionId" className="block text-sm font-medium text-gray-200 mb-2">
                                Session ID
                            </label>
                            <div className="relative">
                                <Key className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                                <input
                                    id="sessionId"
                                    type="text"
                                    value={sessionId}
                                    onChange={(e) => setSessionId(e.target.value)}
                                    placeholder="Enter your session ID"
                                    className="w-full pl-11 pr-4 py-3 bg-white/5 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent transition"
                                />
                            </div>
                        </div>

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
                                    placeholder="your@email.com"
                                    className="w-full pl-11 pr-4 py-3 bg-white/5 border border-white/20 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent transition"
                                    autoComplete="email"
                                />
                            </div>
                        </div>

                        <button
                            type="submit"
                            disabled={isLoading}
                            className="w-full py-3 px-4 bg-gradient-to-r from-emerald-500 to-teal-600 text-white font-semibold rounded-lg shadow-lg hover:from-emerald-600 hover:to-teal-700 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2 focus:ring-offset-slate-900 transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                        >
                            {isLoading ? (
                                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white" />
                            ) : (
                                <>
                                    Access Interview Portal
                                    <ArrowRight className="w-5 h-5" />
                                </>
                            )}
                        </button>
                    </form>

                    <div className="mt-6 text-center text-sm text-gray-400">
                        <p>
                            Are you a recruiter?{' '}
                            <a href="/login" className="text-teal-400 hover:text-teal-300 transition">
                                Sign in here
                            </a>
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

// Helper to get candidate session
export function getCandidateSession(): CandidateSession | null {
    const stored = localStorage.getItem(CANDIDATE_SESSION_KEY);
    if (!stored) return null;
    try {
        return JSON.parse(stored) as CandidateSession;
    } catch {
        return null;
    }
}

// Helper to clear candidate session
export function clearCandidateSession(): void {
    localStorage.removeItem(CANDIDATE_SESSION_KEY);
}
