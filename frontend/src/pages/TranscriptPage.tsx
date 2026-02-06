import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
    ArrowLeft, FileText, AlertTriangle, CheckCircle, Clock, Mic
} from 'lucide-react';
import toast from 'react-hot-toast';
import { interviewApi } from '../services/api';
import type { Interview } from '../types';

export default function TranscriptPage() {
    const { interviewId } = useParams<{ interviewId: string }>();
    const navigate = useNavigate();
    const [interview, setInterview] = useState<Interview | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (interviewId) {
            loadInterview();
        }
    }, [interviewId]);

    const loadInterview = async () => {
        try {
            const data = await interviewApi.get(interviewId!);
            setInterview(data);
        } catch (err) {
            toast.error('Failed to load interview transcript');
            navigate('/candidates');
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-screen">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600" />
            </div>
        );
    }

    if (!interview) return null;

    const transcript = interview.transcript || [];

    return (
        <div className="max-w-4xl mx-auto py-8 px-4 space-y-6">
            {/* Header */}
            <div className="flex items-center gap-4 mb-6">
                <button
                    onClick={() => navigate('/candidates')}
                    className="p-2 hover:bg-gray-100 rounded-full transition-colors"
                >
                    <ArrowLeft className="w-6 h-6 text-gray-600" />
                </button>
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-3">
                        Interview Transcript
                        <span className={`text-sm px-3 py-1 rounded-full ${interview.status === 'completed' ? 'bg-green-100 text-green-700' :
                                interview.status === 'terminated' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'
                            }`}>
                            {interview.status}
                        </span>
                    </h1>
                    <p className="text-gray-500 text-sm mt-1">
                        ID: {interview.interview_id}
                    </p>
                </div>
            </div>

            {/* Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="card flex items-center gap-4">
                    <div className="p-3 bg-blue-50 text-blue-600 rounded-lg">
                        <FileText className="w-6 h-6" />
                    </div>
                    <div>
                        <p className="text-sm text-gray-500">Questions Asked</p>
                        <p className="text-xl font-bold">{transcript.length}</p>
                    </div>
                </div>
                <div className="card flex items-center gap-4">
                    <div className="p-3 bg-green-50 text-green-600 rounded-lg">
                        <Clock className="w-6 h-6" />
                    </div>
                    <div>
                        <p className="text-sm text-gray-500">Duration</p>
                        <p className="text-xl font-bold">
                            {interview.started_at ? new Date(interview.started_at).toLocaleDateString() : 'N/A'}
                        </p>
                    </div>
                </div>
            </div>

            {/* Transcript List */}
            <div className="space-y-6">
                <h2 className="text-xl font-semibold">Q&A History</h2>

                {transcript.length === 0 ? (
                    <div className="card text-center py-12 text-gray-500">
                        No questions recorded for this interview.
                    </div>
                ) : (
                    transcript.map((item: any, index: number) => (
                        <div key={index} className="card border dark:border-gray-700">
                            {/* Question Header */}
                            <div className="flex items-start gap-4 mb-4">
                                <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center font-bold flex-shrink-0">
                                    Q{index + 1}
                                </div>
                                <div className="flex-1">
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className="badge-blue text-xs">{item.pillar || 'General'}</span>
                                        {item.is_follow_up && <span className="badge-yellow text-xs">Follow-up</span>}
                                    </div>
                                    <p className="font-medium text-lg text-gray-900 dark:text-gray-100">
                                        {item.question}
                                    </p>
                                </div>
                            </div>

                            {/* Answer Section */}
                            <div className="pl-12 space-y-3">
                                <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 relative">
                                    <div className="absolute top-4 left-4 text-gray-400">
                                        <Mic className="w-5 h-5" />
                                    </div>
                                    <p className="pl-8 text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed">
                                        {item.answer || <span className="italic text-gray-400">No answer recorded</span>}
                                    </p>
                                </div>

                                {/* Integrity Flags */}
                                {item.cheating_details && item.cheating_details.is_flagged && (
                                    <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex gap-3 text-red-800 text-sm">
                                        <AlertTriangle className="w-5 h-5 flex-shrink-0" />
                                        <div>
                                            <p className="font-semibold">Integrity Flag: {item.cheating_flag}</p>
                                            <ul className="list-disc pl-4 mt-1">
                                                {item.cheating_details.reasons?.map((r: string, i: number) => (
                                                    <li key={i}>{r}</li>
                                                ))}
                                            </ul>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}
