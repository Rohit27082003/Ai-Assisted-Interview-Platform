
import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, CheckCircle, XCircle, BarChart2, Brain, FileText, Briefcase, Wrench, Layers, Share2 } from 'lucide-react';
import toast from 'react-hot-toast';
import { candidateApi } from '../services/api';
import type { Candidate } from '../types';

export default function ResumeAnalysisPage() {
    const { candidateId } = useParams<{ candidateId: string }>();
    const navigate = useNavigate();
    const [candidate, setCandidate] = useState<Candidate | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (candidateId) {
            loadCandidate(candidateId);
        }
    }, [candidateId]);

    const loadCandidate = async (id: string) => {
        try {
            const data = await candidateApi.get(id);
            setCandidate(data);
        } catch (error) {
            console.error(error);
            toast.error('Failed to load candidate details');
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

    if (!candidate) return null;

    const analysis = candidate.scoring_analysis;
    const isShortlisted = candidate.status === 'shortlisted' || ['interviewing', 'interviewed', 'evaluated', 'reported', 'focus_ready'].includes(candidate.status);

    // Safe access to scores with defaults
    const scores = {
        projects: (analysis?.projects_score || 0) * 100,
        skills: (analysis?.skills_score || 0) * 100,
        vector: (analysis?.vector_score || 0) * 100,
        experience: (analysis?.experience_score || 0) * 100,
        tooling: (analysis?.tooling_score || 0) * 100,
        final: (candidate.shortlist_score || 0) * 100,
    };

    const reasoning = analysis?.reasoning as string || "No detailed reasoning available.";

    return (
        <div className="max-w-5xl mx-auto space-y-6 pb-12">
            {/* Header & Back Button */}
            <div className="flex items-center gap-4">
                <button
                    onClick={() => navigate(-1)}
                    className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full transition-colors"
                >
                    <ArrowLeft className="w-6 h-6 text-gray-600 dark:text-gray-400" />
                </button>
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-3">
                        Resume Analysis: {candidate.name}
                        <span className={`px-3 py-1 rounded-full text-sm font-medium ${isShortlisted
                                ? 'bg-green-100 text-green-800 border border-green-200'
                                : 'bg-red-100 text-red-800 border border-red-200'
                            }`}>
                            {candidate.status.toUpperCase().replace('_', ' ')}
                        </span>
                    </h1>
                    <p className="text-gray-500">{candidate.email}</p>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                {/* Left Column: Overall Score Card */}
                <div className="lg:col-span-1 space-y-6">
                    <div className="card text-center p-8 bg-gradient-to-br from-white to-gray-50 dark:from-gray-800 dark:to-gray-900 border-2 border-primary-100 dark:border-primary-900">
                        <h2 className="text-lg font-semibold text-gray-600 dark:text-gray-400 mb-4">Overall Fit Score</h2>
                        <div className="relative inline-flex items-center justify-center">
                            <svg className="w-40 h-40">
                                <circle
                                    className="text-gray-200 dark:text-gray-700"
                                    strokeWidth="12"
                                    stroke="currentColor"
                                    fill="transparent"
                                    r="70"
                                    cx="80"
                                    cy="80"
                                />
                                <circle
                                    className={`${isShortlisted ? 'text-green-500' : 'text-red-500'} transition-all duration-1000 ease-out`}
                                    strokeWidth="12"
                                    strokeDasharray={440}
                                    strokeDashoffset={440 - (440 * scores.final) / 100}
                                    strokeLinecap="round"
                                    stroke="currentColor"
                                    fill="transparent"
                                    r="70"
                                    cx="80"
                                    cy="80"
                                    transform="rotate(-90 80 80)"
                                />
                            </svg>
                            <div className="absolute text-center">
                                <span className="text-4xl font-bold block">{scores.final.toFixed(0)}%</span>
                                <span className="text-xs text-gray-500">MATCH</span>
                            </div>
                        </div>

                        <div className="mt-6 flex justify-center">
                            {isShortlisted ? (
                                <div className="flex items-center gap-2 text-green-600 bg-green-50 px-4 py-2 rounded-lg font-semibold">
                                    <CheckCircle className="w-5 h-5" />
                                    RECOMMENDED
                                </div>
                            ) : (
                                <div className="flex items-center gap-2 text-red-600 bg-red-50 px-4 py-2 rounded-lg font-semibold">
                                    <XCircle className="w-5 h-5" />
                                    NOT RECOMMENDED
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Quick Actions */}
                    <div className="card space-y-3">
                        <h3 className="font-semibold text-gray-700 dark:text-gray-300">Resources</h3>
                        {candidate.resume_s3_url && (
                            <button
                                onClick={async () => {
                                    try {
                                        const result = await candidateApi.getResumeUrl(candidate.candidate_id);
                                        window.open(result.download_url, '_blank');
                                    } catch {
                                        toast.error('Resume unavailable');
                                    }
                                }}
                                className="w-full flex items-center gap-3 p-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors border border-gray-200 dark:border-gray-700 text-left"
                            >
                                <div className="bg-blue-100 p-2 rounded text-blue-600">
                                    <FileText className="w-5 h-5" />
                                </div>
                                <div>
                                    <p className="font-medium">Original Resume</p>
                                    <p className="text-xs text-gray-500">View PDF/Doc</p>
                                </div>
                            </button>
                        )}
                    </div>
                </div>

                {/* Right Column: Detailed Analysis */}
                <div className="lg:col-span-2 space-y-6">

                    {/* Dimensional Breakdown */}
                    <div className="card">
                        <h3 className="text-lg font-bold mb-6 flex items-center gap-2">
                            <BarChart2 className="w-5 h-5 text-primary-600" />
                            Scoring Breakdown
                        </h3>

                        <div className="space-y-6">
                            <ScoreProgress
                                label="Projects & Experience"
                                score={scores.projects}
                                weight="40%"
                                icon={<Briefcase className="w-4 h-4" />}
                                color="bg-blue-500"
                            />
                            <ScoreProgress
                                label="Technical Skills"
                                score={scores.skills}
                                weight="30%"
                                icon={<Layers className="w-4 h-4" />}
                                color="bg-purple-500"
                            />
                            <ScoreProgress
                                label="Semantic Match (AI)"
                                score={scores.vector}
                                weight="15%"
                                icon={<Brain className="w-4 h-4" />}
                                color="bg-indigo-500"
                            />
                            <ScoreProgress
                                label="Work History"
                                score={scores.experience}
                                weight="10%"
                                icon={<Share2 className="w-4 h-4" />}
                                color="bg-orange-500"
                            />
                            <ScoreProgress
                                label="Tools & Technologies"
                                score={scores.tooling}
                                weight="5%"
                                icon={<Wrench className="w-4 h-4" />}
                                color="bg-teal-500"
                            />
                        </div>
                    </div>

                    {/* AI Reasoning */}
                    <div className="card bg-gray-50 dark:bg-gray-800/50 border-gray-200 dark:border-gray-700">
                        <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
                            <Brain className="w-5 h-5 text-primary-600" />
                            AI Analysis & Reasoning
                        </h3>
                        <div className="prose dark:prose-invert max-w-none text-gray-700 dark:text-gray-300 whitespace-pre-line">
                            {reasoning}
                        </div>
                    </div>

                </div>
            </div>
        </div>
    );
}

const ScoreProgress = ({ label, score, weight, icon, color }: any) => (
    <div>
        <div className="flex justify-between items-center mb-1">
            <div className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                <span className="p-1.5 bg-gray-100 dark:bg-gray-800 rounded text-gray-600 dark:text-gray-400">
                    {icon}
                </span>
                {label} <span className="text-xs text-gray-400 font-normal">({weight} weight)</span>
            </div>
            <span className="font-bold text-gray-900 dark:text-white">{score.toFixed(0)}%</span>
        </div>
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5">
            <div
                className={`h-2.5 rounded-full transition-all duration-1000 ease-out ${color}`}
                style={{ width: `${score}%` }}
            />
        </div>
    </div>
);
