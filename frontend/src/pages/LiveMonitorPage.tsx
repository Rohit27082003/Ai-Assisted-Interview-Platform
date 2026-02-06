
import { useEffect, useState, useCallback } from 'react';
import { Activity, StopCircle, RefreshCw, AlertOctagon } from 'lucide-react';
import toast from 'react-hot-toast';
import { interviewApi } from '../services/api';

interface ActiveInterview {
    interview_id: string;
    candidate_name: string;
    candidate_email: string;
    current_pillar: string;
    question_number: number;
    status: string;
}

export default function LiveMonitorPage() {
    const [interviews, setInterviews] = useState<ActiveInterview[]>([]);
    const [loading, setLoading] = useState(true);
    const [terminating, setTerminating] = useState<Record<string, boolean>>({});

    const loadInterviews = useCallback(async () => {
        try {
            const data = await interviewApi.getMonitorActive();
            setInterviews(data);
        } catch (error) {
            console.error('Failed to load active interviews', error);
            // Suppress toast on periodic refresh to avoid spam
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadInterviews();
        const interval = setInterval(loadInterviews, 5000); // Poll every 5 seconds
        return () => clearInterval(interval);
    }, [loadInterviews]);

    const handleTerminate = async (interviewId: string) => {
        if (!window.confirm("ARE YOU SURE? This will immediately stop the candidate's interview session.")) {
            return;
        }

        setTerminating(p => ({ ...p, [interviewId]: true }));
        try {
            await interviewApi.terminate(interviewId);
            toast.success('Interview terminated');
            loadInterviews();
        } catch {
            toast.error('Failed to terminate interview');
        } finally {
            setTerminating(p => ({ ...p, [interviewId]: false }));
        }
    };

    if (loading && interviews.length === 0) {
        return (
            <div className="flex items-center justify-center h-96">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <Activity className="w-8 h-8 text-primary-600" />
                    <div>
                        <h1 className="text-3xl font-bold">Live Monitor</h1>
                        <p className="mt-1 text-gray-600">Real-time supervision of active interviews</p>
                    </div>
                </div>
                <button
                    onClick={loadInterviews}
                    className="btn-secondary flex items-center gap-2"
                >
                    <RefreshCw className="w-4 h-4" /> Refresh
                </button>
            </div>

            <div className="card">
                <div className="flex items-center gap-3 mb-6">
                    <div className={`w-3 h-3 rounded-full ${interviews.length > 0 ? 'bg-green-500 animate-pulse' : 'bg-gray-300'}`} />
                    <h3 className="font-semibold text-lg">
                        Active Sessions ({interviews.length})
                    </h3>
                </div>

                {interviews.length === 0 ? (
                    <div className="text-center py-12 bg-gray-50 rounded-lg border-2 border-dashed border-gray-200">
                        <Activity className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                        <h3 className="text-lg font-medium text-gray-900">No interviews in progress</h3>
                        <p className="text-gray-500">Active sessions will appear here automatically.</p>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full">
                            <thead>
                                <tr className="text-left text-sm text-gray-500 border-b">
                                    <th className="pb-3 font-medium">Candidate</th>
                                    <th className="pb-3 font-medium">Current Focus</th>
                                    <th className="pb-3 font-medium">Question</th>
                                    <th className="pb-3 font-medium">Status</th>
                                    <th className="pb-3 font-medium text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {interviews.map((i) => (
                                    <tr key={i.interview_id} className="border-b last:border-0 group hover:bg-gray-50 transition-colors">
                                        <td className="py-4">
                                            <p className="font-semibold text-gray-900">{i.candidate_name}</p>
                                            <p className="text-sm text-gray-500">{i.candidate_email}</p>
                                        </td>
                                        <td className="py-4">
                                            <span className="badge-blue font-medium">
                                                {i.current_pillar}
                                            </span>
                                        </td>
                                        <td className="py-4 font-mono text-gray-700">
                                            #{i.question_number}
                                        </td>
                                        <td className="py-4">
                                            <span className="flex items-center gap-2 text-green-600 font-medium">
                                                <span className="relative flex h-2 w-2">
                                                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                                                    <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                                                </span>
                                                Live
                                            </span>
                                        </td>
                                        <td className="py-4 text-right">
                                            <button
                                                onClick={() => handleTerminate(i.interview_id)}
                                                disabled={terminating[i.interview_id]}
                                                className="btn-secondary text-red-600 hover:bg-red-50 hover:border-red-200 flex items-center gap-2 ml-auto"
                                                title="Force stop interview"
                                            >
                                                <AlertOctagon className="w-4 h-4" />
                                                {terminating[i.interview_id] ? 'Stopping...' : 'Stop & Terminate'}
                                            </button>
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
