
import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, CheckCircle, XCircle, BarChart2, Brain, FileText, Briefcase, Wrench, Layers, Share2, AlertTriangle } from 'lucide-react';
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
        <div className="min-h-screen bg-gray-950 text-gray-100 p-6 font-sans selection:bg-primary-500/30">
            <div className="max-w-6xl mx-auto space-y-8">
                {/* Header & Back Button */}
                <div className="flex items-center gap-4 mb-8">
                    <button
                        onClick={() => navigate(-1)}
                        className="p-3 bg-gray-900 hover:bg-gray-800 rounded-full transition-all border border-gray-800 hover:border-gray-700 shadow-lg group"
                    >
                        <ArrowLeft className="w-6 h-6 text-gray-400 group-hover:text-white transition-colors" />
                    </button>
                    <div>
                        <h1 className="text-3xl font-bold flex items-center gap-4 text-white tracking-tight">
                            <span className="bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
                                Resume Analysis
                            </span>
                            <span className="text-gray-600">/</span>
                            {candidate.name}
                            <span className={`px-4 py-1.5 rounded-full text-sm font-bold tracking-wide shadow-lg border ${isShortlisted
                                ? 'bg-green-500/10 text-green-400 border-green-500/20 shadow-green-500/10'
                                : 'bg-red-500/10 text-red-400 border-red-500/20 shadow-red-500/10'
                                }`}>
                                {candidate.status.toUpperCase().replace('_', ' ')}
                            </span>
                        </h1>
                        <p className="text-gray-400 font-medium mt-1 flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-gray-600"></span>
                            {candidate.email}
                        </p>
                    </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">

                    {/* Left Column: Score & Stats (4 cols) */}
                    <div className="lg:col-span-4 space-y-6">
                        {/* Overall Score Card */}
                        <div className="card relative overflow-hidden bg-gray-900 border-gray-800 p-8 shadow-2xl flex flex-col items-center">
                            <div className="absolute inset-0 bg-gradient-to-b from-blue-500/5 to-transparent pointer-events-none" />
                            <h2 className="text-gray-400 font-medium uppercase tracking-wider text-sm mb-6">Overall Match Score</h2>
                            <div className="relative inline-flex items-center justify-center">
                                {/* Glow Effect behind chart */}
                                <div className={`absolute inset-0 blur-3xl opacity-20 ${isShortlisted ? 'bg-green-500' : 'bg-red-500'}`} />
                                <svg className="w-48 h-48 relative z-10">
                                    <circle
                                        className="text-gray-800"
                                        strokeWidth="12"
                                        stroke="currentColor"
                                        fill="transparent"
                                        r="80"
                                        cx="96"
                                        cy="96"
                                    />
                                    <circle
                                        className={`${isShortlisted ? 'text-green-500 shadow-[0_0_15px_rgba(34,197,94,0.5)]' : 'text-red-500'} transition-all duration-1000 ease-out`}
                                        strokeWidth="12"
                                        strokeDasharray={502}
                                        strokeDashoffset={502 - (502 * scores.final) / 100}
                                        strokeLinecap="round"
                                        stroke="currentColor"
                                        fill="transparent"
                                        r="80"
                                        cx="96"
                                        cy="96"
                                        transform="rotate(-90 96 96)"
                                    />
                                </svg>
                                <div className="absolute text-center z-10">
                                    <span className="text-5xl font-black block text-white tracking-tighter drop-shadow-lg">{scores.final.toFixed(0)}<span className="text-2xl text-gray-500">%</span></span>
                                    <span className={`text-xs font-bold tracking-widest mt-1 block ${isShortlisted ? 'text-green-400' : 'text-red-400'}`}>MATCH RATE</span>
                                </div>
                            </div>

                            <div className="mt-8 w-full">
                                {isShortlisted ? (
                                    <div className="flex items-center justify-center gap-3 text-green-400 bg-green-500/10 border border-green-500/20 px-4 py-3 rounded-xl font-bold tracking-wide shadow-lg shadow-green-900/20">
                                        <CheckCircle className="w-5 h-5" />
                                        HIGHLY RECOMMENDED
                                    </div>
                                ) : (
                                    <div className="flex items-center justify-center gap-3 text-red-400 bg-red-500/10 border border-red-500/20 px-4 py-3 rounded-xl font-bold tracking-wide shadow-lg shadow-red-900/20">
                                        <XCircle className="w-5 h-5" />
                                        NOT RECOMMENDED
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Quick Actions */}
                        <div className="card bg-gray-900 border-gray-800 p-6 shadow-xl">
                            <h3 className="text-gray-400 font-medium uppercase tracking-wider text-sm mb-4">Source Documents</h3>
                            {candidate.resume_s3_url ? (
                                <button
                                    onClick={async () => {
                                        try {
                                            const result = await candidateApi.getResumeUrl(candidate.candidate_id);
                                            window.open(result.download_url, '_blank');
                                        } catch {
                                            toast.error('Resume unavailable');
                                        }
                                    }}
                                    className="w-full group flex items-center gap-4 p-4 rounded-xl bg-gray-800/50 hover:bg-gray-800 border border-gray-700 hover:border-blue-500/30 transition-all duration-300 text-left"
                                >
                                    <div className="bg-blue-500/10 p-3 rounded-lg text-blue-400 group-hover:text-blue-300 group-hover:bg-blue-500/20 transition-colors">
                                        <FileText className="w-6 h-6" />
                                    </div>
                                    <div>
                                        <p className="font-bold text-gray-200 group-hover:text-white transition-colors">Original Resume</p>
                                        <p className="text-xs text-gray-500 group-hover:text-gray-400 mt-0.5">PDF Document • Click to view</p>
                                    </div>
                                    <ArrowLeft className="w-4 h-4 text-gray-600 rotate-180 ml-auto group-hover:translate-x-1 transition-transform" />
                                </button>
                            ) : (
                                <div className="text-gray-500 text-sm italic p-4 text-center bg-gray-800/30 rounded-lg">No resume document available</div>
                            )}
                        </div>
                    </div>

                    {/* Right Column: Detailed Analysis (8 cols) */}
                    <div className="lg:col-span-8 space-y-6">

                        {/* Dimensional Breakdown */}
                        <div className="card bg-gray-900 border-gray-800 p-8 shadow-xl">
                            <h3 className="text-xl font-bold mb-6 flex items-center gap-3 text-white">
                                <div className="p-2 bg-purple-500/10 rounded-lg text-purple-400">
                                    <BarChart2 className="w-6 h-6" />
                                </div>
                                Scoring Breakdown
                            </h3>

                            <div className="space-y-6">
                                <ScoreProgress
                                    label="Projects"
                                    score={scores.projects}
                                    weight="30%"
                                    icon={<Briefcase className="w-4 h-4" />}
                                    color="bg-gradient-to-r from-blue-600 to-cyan-400 shadow-[0_0_10px_rgba(56,189,248,0.4)]"
                                    iconColor="text-cyan-400 bg-cyan-900/20"
                                />
                                <ScoreProgress
                                    label="Technical Skills"
                                    score={scores.skills}
                                    weight="25%"
                                    icon={<Layers className="w-4 h-4" />}
                                    color="bg-gradient-to-r from-purple-600 to-pink-500 shadow-[0_0_10px_rgba(236,72,153,0.4)]"
                                    iconColor="text-pink-400 bg-pink-900/20"
                                />
                                <ScoreProgress
                                    label="Work Experience"
                                    score={scores.experience}
                                    weight="25%"
                                    icon={<Share2 className="w-4 h-4" />}
                                    color="bg-gradient-to-r from-orange-600 to-amber-400 shadow-[0_0_10px_rgba(251,191,36,0.4)]"
                                    iconColor="text-amber-400 bg-amber-900/20"
                                />
                                <ScoreProgress
                                    label="Semantic Match (AI)"
                                    score={scores.vector}
                                    weight="15%"
                                    icon={<Brain className="w-4 h-4" />}
                                    color="bg-gradient-to-r from-indigo-600 to-violet-400 shadow-[0_0_10px_rgba(139,92,246,0.4)]"
                                    iconColor="text-violet-400 bg-violet-900/20"
                                />
                                <ScoreProgress
                                    label="Tools & Technologies"
                                    score={scores.tooling}
                                    weight="5%"
                                    icon={<Wrench className="w-4 h-4" />}
                                    color="bg-gradient-to-r from-emerald-600 to-lime-400 shadow-[0_0_10px_rgba(163,230,53,0.4)]"
                                    iconColor="text-lime-400 bg-lime-900/20"
                                />
                            </div>
                        </div>

                        {/* AI Reasoning */}
                        <div className="card bg-gray-900 border-gray-800 p-8 shadow-xl relative overflow-hidden">
                            <div className="absolute top-0 right-0 w-64 h-64 bg-primary-500/5 rounded-full blur-3xl -mr-32 -mt-32 pointer-events-none" />
                            <h3 className="text-xl font-bold mb-5 flex items-center gap-3 text-white relative z-10">
                                <div className="p-2 bg-indigo-500/10 rounded-lg text-indigo-400">
                                    <Brain className="w-6 h-6" />
                                </div>
                                AI Analysis & Reasoning
                            </h3>
                            <div className="prose prose-invert max-w-none text-gray-300 leading-relaxed font-medium relative z-10">
                                {reasoning}
                            </div>
                        </div>

                        {/* Detailed Insights Grid */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            {/* Pros */}
                            {analysis?.pros && analysis.pros.length > 0 && (
                                <div className="card overflow-hidden border-green-900/50 bg-gray-900 p-0 shadow-lg group hover:border-green-800 transition-colors">
                                    <div className="bg-green-950/30 px-6 py-4 border-b border-green-900/50 flex items-center gap-3">
                                        <div className="p-2 bg-green-900/50 rounded-lg text-green-400 border border-green-800/50">
                                            <CheckCircle className="w-5 h-5" />
                                        </div>
                                        <h4 className="font-bold text-green-100 text-lg">
                                            Strengths
                                        </h4>
                                    </div>
                                    <div className="p-6">
                                        <ul className="space-y-4">
                                            {analysis.pros.map((item, i) => (
                                                <li key={i} className="text-gray-300 flex items-start gap-3 text-sm leading-relaxed font-medium">
                                                    <span className="mt-1.5 w-1.5 h-1.5 bg-green-500 rounded-full flex-shrink-0 shadow-[0_0_8px_rgba(34,197,94,0.6)]" />
                                                    {item}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                </div>
                            )}

                            {/* Cons */}
                            {analysis?.cons && analysis.cons.length > 0 && (
                                <div className="card overflow-hidden border-orange-900/50 bg-gray-900 p-0 shadow-lg group hover:border-orange-800 transition-colors">
                                    <div className="bg-orange-950/30 px-6 py-4 border-b border-orange-900/50 flex items-center gap-3">
                                        <div className="p-2 bg-orange-900/50 rounded-lg text-orange-400 border border-orange-800/50">
                                            <Brain className="w-5 h-5" />
                                        </div>
                                        <h4 className="font-bold text-orange-100 text-lg">
                                            Gaps & Weaknesses
                                        </h4>
                                    </div>
                                    <div className="p-6">
                                        <ul className="space-y-4">
                                            {analysis.cons.map((item, i) => (
                                                <li key={i} className="text-gray-300 flex items-start gap-3 text-sm leading-relaxed font-medium">
                                                    <span className="mt-1.5 w-1.5 h-1.5 bg-orange-500 rounded-full flex-shrink-0 shadow-[0_0_8px_rgba(249,115,22,0.6)]" />
                                                    {item}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                </div>
                            )}

                            {/* Missing Skills */}
                            {analysis?.missing_critical_skills && analysis.missing_critical_skills.length > 0 && (
                                <div className="card overflow-hidden border-red-900/50 bg-gray-900 p-0 shadow-lg group hover:border-red-800 transition-colors">
                                    <div className="bg-red-950/30 px-6 py-4 border-b border-red-900/50 flex items-center gap-3">
                                        <div className="p-2 bg-red-900/50 rounded-lg text-red-400 border border-red-800/50">
                                            <XCircle className="w-5 h-5" />
                                        </div>
                                        <h4 className="font-bold text-red-100 text-lg">
                                            Missing Critical Skills
                                        </h4>
                                    </div>
                                    <div className="p-6">
                                        <ul className="space-y-4">
                                            {analysis.missing_critical_skills.map((skill, i) => (
                                                <li key={i} className="text-gray-300 flex items-start gap-3 text-sm leading-relaxed font-medium">
                                                    <span className="mt-1.5 w-1.5 h-1.5 bg-red-500 rounded-full flex-shrink-0 shadow-[0_0_8px_rgba(239,68,68,0.6)]" />
                                                    {skill}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                </div>
                            )}

                            {/* Red Flags - Special Emphasis */}
                            {analysis?.red_flags && analysis.red_flags.length > 0 && (
                                <div className="card overflow-hidden border-red-600/60 bg-gray-900 p-0 shadow-lg ring-1 ring-red-500/20 hover:ring-red-500/40 transition-all">
                                    <div className="bg-red-950/60 px-6 py-4 border-b border-red-600/60 flex items-center gap-3">
                                        <div className="p-2 bg-red-900 rounded-lg text-white shadow-lg shadow-red-900/50">
                                            <AlertTriangle className="w-5 h-5" />
                                        </div>
                                        <h4 className="font-bold text-white text-lg tracking-wide">
                                            Potential Red Flags
                                        </h4>
                                    </div>
                                    <div className="p-6 bg-gradient-to-br from-gray-900 via-gray-900 to-red-950/20">
                                        <ul className="space-y-4">
                                            {analysis.red_flags.map((flag, i) => (
                                                <li key={i} className="text-gray-200 flex items-start gap-3 text-sm leading-relaxed font-bold">
                                                    <span className="mt-1.5 w-1.5 h-1.5 bg-red-500 rounded-full flex-shrink-0 shadow-[0_0_10px_rgba(239,68,68,0.8)]" />
                                                    {flag}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                </div>
                            )}
                        </div>

                    </div>
                </div>
            </div>
        </div>
    );
}

const ScoreProgress = ({ label, score, weight, icon, color, iconColor }: any) => (
    <div>
        <div className="flex justify-between items-center mb-2">
            <div className="flex items-center gap-3 text-sm font-medium text-gray-300">
                <span className={`p-1.5 rounded-md ${iconColor || 'bg-gray-800 text-gray-400'}`}>
                    {icon}
                </span>
                <span className="tracking-wide">{label}</span>
                <span className="text-xs text-gray-500 font-medium ml-1 px-2 py-0.5 bg-gray-800 rounded-full border border-gray-700">Weight: {weight}</span>
            </div>
            <span className="font-bold text-white font-mono text-lg">{score.toFixed(0)}%</span>
        </div>
        <div className="w-full bg-gray-800/50 rounded-full h-3 border border-gray-700/50 overflow-hidden">
            <div
                className={`h-full rounded-full transition-all duration-1000 ease-out ${color}`}
                style={{ width: `${score}%` }}
            />
        </div>
    </div>
);
