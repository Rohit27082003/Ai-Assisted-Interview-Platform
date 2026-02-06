import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, Clock, CheckCircle, XCircle, Briefcase, User, LogOut } from 'lucide-react';
import toast from 'react-hot-toast';
import { getCandidateSession, clearCandidateSession } from './CandidateLoginPage';

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
        } catch (err) {
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
            toast.success('Interview started!');
            navigate(`/candidate/interview/${data.interview_id}`);
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Failed to start interview';
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
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-emerald-900 via-teal-900 to-slate-900">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white" />
            </div>
        );
    }

    if (!portalInfo) {
        return null;
    }

    const getStatusIcon = () => {
        switch (portalInfo.interview_status) {
            case 'completed':
                return <CheckCircle className="w-6 h-6 text-green-400" />;
            case 'in_progress':
                return <Clock className="w-6 h-6 text-yellow-400" />;
            case 'terminated':
                return <XCircle className="w-6 h-6 text-red-400" />;
            default:
                return <Clock className="w-6 h-6 text-gray-400" />;
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
        <div className="min-h-screen bg-gradient-to-br from-emerald-900 via-teal-900 to-slate-900 py-12 px-4">
            <div className="max-w-3xl mx-auto">
                {/* Header */}
                <div className="flex items-center justify-between mb-8">
                    <div>
                        <h1 className="text-3xl font-bold text-white">Interview Portal</h1>
                        <p className="text-teal-300">Welcome back!</p>
                    </div>
                    <button
                        onClick={handleLogout}
                        className="flex items-center gap-2 text-gray-400 hover:text-white transition"
                    >
                        <LogOut className="w-5 h-5" />
                        Logout
                    </button>
                </div>

                {/* Candidate Info Card */}
                <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-6 mb-6 border border-white/20">
                    <div className="flex items-start gap-4">
                        <div className="w-14 h-14 bg-gradient-to-br from-emerald-500 to-teal-600 rounded-xl flex items-center justify-center">
                            <User className="w-7 h-7 text-white" />
                        </div>
                        <div className="flex-1">
                            <h2 className="text-xl font-semibold text-white">{portalInfo.name}</h2>
                            <p className="text-gray-400">{portalInfo.email}</p>
                        </div>
                    </div>

                    <div className="mt-4 pt-4 border-t border-white/10">
                        <div className="flex items-center gap-2 text-gray-300">
                            <Briefcase className="w-5 h-5 text-teal-400" />
                            <span>Position: <strong className="text-white">{portalInfo.job_title}</strong></span>
                        </div>
                    </div>
                </div>

                {/* Interview Status Card */}
                <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-6 mb-6 border border-white/20">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="text-lg font-semibold text-white">Interview Status</h3>
                        <div className="flex items-center gap-2">
                            {getStatusIcon()}
                            <span className="text-gray-300">{getStatusText()}</span>
                        </div>
                    </div>

                    <div className="bg-slate-800/50 rounded-lg p-4 text-gray-300 whitespace-pre-line">
                        {portalInfo.instructions}
                    </div>

                    {portalInfo.can_start_interview && (
                        <button
                            onClick={handleStartInterview}
                            disabled={startingInterview}
                            className="mt-6 w-full py-4 px-6 bg-gradient-to-r from-emerald-500 to-teal-600 text-white text-lg font-semibold rounded-xl shadow-lg hover:from-emerald-600 hover:to-teal-700 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2 focus:ring-offset-slate-900 transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3"
                        >
                            {startingInterview ? (
                                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-white" />
                            ) : (
                                <>
                                    <Play className="w-6 h-6" />
                                    Start Interview
                                </>
                            )}
                        </button>
                    )}

                    {portalInfo.interview_status === 'in_progress' && portalInfo.interview_id && (
                        <button
                            onClick={() => navigate(`/candidate/interview/${portalInfo.interview_id}`)}
                            className="mt-6 w-full py-4 px-6 bg-gradient-to-r from-yellow-500 to-orange-600 text-white text-lg font-semibold rounded-xl shadow-lg hover:from-yellow-600 hover:to-orange-700 transition flex items-center justify-center gap-3"
                        >
                            <Play className="w-6 h-6" />
                            Continue Interview
                        </button>
                    )}
                </div>

                {/* Tips Card */}
                <div className="bg-teal-500/10 border border-teal-500/30 rounded-2xl p-6">
                    <h3 className="text-lg font-semibold text-teal-300 mb-3">Tips for Success</h3>
                    <ul className="space-y-2 text-teal-200/80">
                        <li className="flex items-start gap-2">
                            <span className="text-teal-400">•</span>
                            Ensure you're in a quiet environment with good lighting
                        </li>
                        <li className="flex items-start gap-2">
                            <span className="text-teal-400">•</span>
                            Test your microphone before starting
                        </li>
                        <li className="flex items-start gap-2">
                            <span className="text-teal-400">•</span>
                            Take your time to read each question carefully
                        </li>
                        <li className="flex items-start gap-2">
                            <span className="text-teal-400">•</span>
                            Speak clearly and at a moderate pace
                        </li>
                        <li className="flex items-start gap-2">
                            <span className="text-teal-400">•</span>
                            Stay focused and avoid multitasking during the interview
                        </li>
                    </ul>
                </div>
            </div>
        </div>
    );
}
