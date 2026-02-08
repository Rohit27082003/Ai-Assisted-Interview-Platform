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
        <div className="min-h-screen bg-gray-50 text-gray-900 font-sans py-8 px-4">
            <div className="max-w-4xl mx-auto space-y-8">
                {/* Header */}
                <div className="flex items-center gap-4 mb-6">
                    <button
                        onClick={() => navigate('/candidates')}
                        className="p-3 bg-white hover:bg-gray-100 border border-gray-200 rounded-full transition-all shadow-sm group"
                    >
                        <ArrowLeft className="w-6 h-6 text-gray-700 group-hover:text-gray-900" />
                    </button>
                    <div>
                        <h1 className="text-3xl font-extrabold flex items-center gap-3 text-gray-900 tracking-tight">
                            Interview Transcript
                            <span className={`text-sm px-3 py-1 rounded-full font-bold border ${interview.status === 'completed' ? 'bg-green-100 text-green-800 border-green-200' :
                                interview.status === 'terminated' ? 'bg-red-100 text-red-800 border-red-200' : 'bg-blue-100 text-blue-800 border-blue-200'
                                }`}>
                                {interview.status.toUpperCase()}
                            </span>
                        </h1>
                        <p className="text-gray-600 font-medium mt-1">
                            ID: <span className="font-mono text-gray-800">{interview.interview_id}</span>
                        </p>
                    </div>
                </div>

                {/* Stats Cards */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="bg-white border-l-4 border-blue-500 p-6 rounded-r-xl shadow-sm flex items-center gap-4 transition-transform hover:-translate-y-1">
                        <div className="p-3 bg-blue-100 text-blue-700 rounded-lg">
                            <FileText className="w-6 h-6" />
                        </div>
                        <div>
                            <p className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Questions</p>
                            <p className="text-2xl font-black text-gray-900">{transcript.length}</p>
                        </div>
                    </div>
                    <div className="bg-white border-l-4 border-green-500 p-6 rounded-r-xl shadow-sm flex items-center gap-4 transition-transform hover:-translate-y-1">
                        <div className="p-3 bg-green-100 text-green-700 rounded-lg">
                            <Clock className="w-6 h-6" />
                        </div>
                        <div>
                            <p className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Date</p>
                            <p className="text-2xl font-black text-gray-900">
                                {interview.started_at ? new Date(interview.started_at).toLocaleDateString() : 'N/A'}
                            </p>
                        </div>
                    </div>
                </div>

                {/* Transcript List */}
                <div className="space-y-8">
                    <h2 className="text-2xl font-bold text-gray-900 border-b-2 border-gray-200 pb-2">
                        Q&A History
                    </h2>

                    {transcript.length === 0 ? (
                        <div className="bg-white border border-gray-200 rounded-xl p-12 text-center text-gray-500 shadow-sm">
                            <p className="text-lg font-medium">No questions recorded for this interview.</p>
                        </div>
                    ) : (
                        transcript.map((item: any, index: number) => (
                            <div key={index} className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden hover:shadow-md transition-shadow">
                                {/* Question Header */}
                                <div className="bg-gray-50 px-6 py-5 border-b border-gray-200 flex items-start gap-4">
                                    <div className="w-10 h-10 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold text-lg flex-shrink-0 shadow-sm">
                                        Q{index + 1}
                                    </div>
                                    <div className="flex-1">
                                        <div className="flex items-center gap-2 mb-2">
                                            <span className="px-2 py-0.5 rounded text-xs font-bold bg-blue-100 text-blue-800 uppercase tracking-wider">
                                                {item.pillar || 'General'}
                                            </span>
                                            {item.is_follow_up && (
                                                <span className="px-2 py-0.5 rounded text-xs font-bold bg-yellow-100 text-yellow-800 uppercase tracking-wider flex items-center gap-1">
                                                    Follow-up
                                                </span>
                                            )}
                                        </div>
                                        <p className="font-bold text-xl text-gray-900 leading-snug">
                                            {item.question}
                                        </p>
                                    </div>
                                </div>

                                {/* Answer Section */}
                                <div className="p-6 pl-20">
                                    <div className="relative">
                                        <div className="absolute top-0 left-[-40px] p-2 bg-gray-100 rounded-lg text-gray-500">
                                            <Mic className="w-5 h-5" />
                                        </div>
                                        <div className="prose max-w-none text-gray-900 text-lg leading-relaxed font-medium">
                                            {item.answer ? (
                                                <p>{item.answer}</p>
                                            ) : (
                                                <p className="italic text-gray-400">No answer recorded</p>
                                            )}
                                        </div>
                                    </div>

                                    {/* Integrity Flags */}
                                    {item.cheating_details && item.cheating_details.is_flagged && (
                                        <div className="mt-6 bg-red-50 border-l-4 border-red-600 rounded-r-lg p-4 flex gap-4 animate-pulse-slow">
                                            <div className="p-2 bg-red-100 rounded-full text-red-600 h-fit">
                                                <AlertTriangle className="w-6 h-6" />
                                            </div>
                                            <div>
                                                <p className="font-bold text-red-900 text-lg">Integrity Flag: {item.cheating_flag}</p>
                                                <ul className="list-disc pl-5 mt-1 space-y-1 text-red-800 font-medium">
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
        </div>
    );
}
