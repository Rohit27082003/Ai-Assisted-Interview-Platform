import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  CheckCircle, XCircle, AlertTriangle, Award, TrendingUp,
  TrendingDown, Shield, FileText, ArrowLeft
} from 'lucide-react';
import toast from 'react-hot-toast';
import { evaluationApi } from '../services/api';
import type { Report, EvaluationResponse } from '../types';

export default function ReportPage() {
  const { interviewId } = useParams<{ interviewId: string }>();
  const navigate = useNavigate();
  const [report, setReport] = useState<Report | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    if (interviewId) loadReport();
  }, [interviewId]);

  const loadReport = async () => {
    try {
      const data = await evaluationApi.getReport(interviewId!);
      setReport(data);
    } catch {
      // Report might not exist yet
    } finally {
      setLoading(false);
    }
  };

  const handleEvaluate = async () => {
    if (!interviewId) return;
    setGenerating(true);
    try {
      const evalResult = await evaluationApi.evaluate(interviewId);
      setEvaluation(evalResult);
      toast.success('Evaluation complete');
    } catch {
      toast.error('Evaluation failed');
    } finally {
      setGenerating(false);
    }
  };

  const handleGenerateReport = async () => {
    if (!interviewId) return;
    setGenerating(true);
    try {
      const reportData = await evaluationApi.generateReport(interviewId);
      setReport(reportData);
      toast.success('Report generated');
    } catch {
      toast.error('Report generation failed');
    } finally {
      setGenerating(false);
    }
  };

  const getRecommendationDisplay = (rec: string) => {
    switch (rec) {
      case 'hire':
        return { icon: CheckCircle, color: 'text-green-600', bg: 'bg-green-50', label: 'HIRE' };
      case 'no_hire':
        return { icon: XCircle, color: 'text-red-600', bg: 'bg-red-50', label: 'NO HIRE' };
      default:
        return { icon: AlertTriangle, color: 'text-yellow-600', bg: 'bg-yellow-50', label: 'BORDERLINE' };
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600" />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="max-w-2xl mx-auto text-center py-20 space-y-6">
        <FileText className="w-16 h-16 text-gray-400 mx-auto" />
        <h2 className="text-2xl font-bold">No Report Yet</h2>
        <p className="text-gray-600">
          Run the evaluation and report generation pipeline for this interview.
        </p>
        <div className="flex gap-4 justify-center">
          <button className="btn-secondary" onClick={() => navigate('/candidates')}>
            <ArrowLeft className="w-4 h-4 inline mr-2" /> Back
          </button>
          {!evaluation ? (
            <button className="btn-primary" onClick={handleEvaluate} disabled={generating}>
              {generating ? 'Evaluating...' : 'Run Evaluation'}
            </button>
          ) : (
            <button className="btn-primary" onClick={handleGenerateReport} disabled={generating}>
              {generating ? 'Generating...' : 'Generate Report'}
            </button>
          )}
        </div>

        {evaluation && (
          <div className="card text-left mt-8">
            <h3 className="font-semibold mb-4">Evaluation Results</h3>
            <p className="text-2xl font-bold text-primary-600 mb-4">
              Average Score: {evaluation.average_score.toFixed(2)} / 5
            </p>
            <div className="space-y-3">
              {evaluation.evaluations.map((ev, i) => (
                <div key={i} className="border rounded-lg p-3">
                  <p className="font-medium">{ev.question}</p>
                  <div className="flex gap-4 mt-2 text-sm">
                    <span>Correctness: {ev.correctness}/5</span>
                    <span>Depth: {ev.depth}/5</span>
                    <span>Reasoning: {ev.reasoning}/5</span>
                    <span>Clarity: {ev.clarity}/5</span>
                  </div>
                  <p className="text-sm text-gray-500 mt-1">{ev.justification}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  const rec = getRecommendationDisplay(report.recommendation);
  const RecIcon = rec.icon;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <button className="btn-secondary mb-4" onClick={() => navigate('/candidates')}>
        <ArrowLeft className="w-4 h-4 inline mr-2" /> Back to Candidates
      </button>

      {/* Report Header */}
      <div className="card">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold">{report.candidate_name}</h1>
            <p className="text-gray-600">{report.jd_title}</p>
            <p className="text-sm text-gray-500 mt-1">
              Generated {new Date(report.created_at).toLocaleString()}
            </p>
          </div>
          <div className={`${rec.bg} px-6 py-4 rounded-xl text-center`}>
            <RecIcon className={`w-10 h-10 ${rec.color} mx-auto mb-2`} />
            <p className={`text-xl font-bold ${rec.color}`}>{rec.label}</p>
            <p className="text-sm text-gray-600">
              Confidence: {(report.confidence_score * 100).toFixed(0)}%
            </p>
          </div>
        </div>
      </div>

      {/* Score Overview */}
      <div className="grid grid-cols-2 gap-6">
        <div className="card text-center">
          <Award className="w-8 h-8 text-primary-600 mx-auto mb-2" />
          <p className="text-4xl font-bold text-primary-600">
            {report.final_score.toFixed(2)}
          </p>
          <p className="text-gray-500">Overall Score / 5</p>
        </div>
        <div className="card">
          <h3 className="font-semibold mb-3">Topic Scores</h3>
          <div className="space-y-2">
            {Object.entries(report.topic_scores).map(([topic, score]) => (
              <div key={topic} className="flex items-center justify-between">
                <span className="text-sm font-medium">{topic}</span>
                <div className="flex items-center gap-2">
                  <div className="w-32 bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-primary-600 rounded-full h-2"
                      style={{ width: `${(score / 5) * 100}%` }}
                    />
                  </div>
                  <span className="text-sm font-bold w-8">{score.toFixed(1)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Strengths & Weaknesses */}
      <div className="grid grid-cols-2 gap-6">
        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-5 h-5 text-green-600" />
            <h3 className="font-semibold">Strengths</h3>
          </div>
          <ul className="space-y-2">
            {report.strengths.map((s, i) => (
              <li key={i} className="flex items-start gap-2">
                <CheckCircle className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
                <span className="text-sm">{s}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <TrendingDown className="w-5 h-5 text-red-600" />
            <h3 className="font-semibold">Weaknesses</h3>
          </div>
          <ul className="space-y-2">
            {report.weaknesses.map((w, i) => (
              <li key={i} className="flex items-start gap-2">
                <XCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                <span className="text-sm">{w}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Cheating Flags */}
      {report.cheating_flags.length > 0 && (
        <div className="card bg-yellow-50 border-yellow-200">
          <div className="flex items-center gap-2 mb-4">
            <Shield className="w-5 h-5 text-yellow-600" />
            <h3 className="font-semibold text-yellow-800">
              Integrity Flags ({report.cheating_flags.length})
            </h3>
          </div>
          <ul className="space-y-2">
            {report.cheating_flags.map((f, i) => (
              <li key={i} className="text-sm text-yellow-700 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                {f}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Summary */}
      <div className="card">
        <h3 className="font-semibold mb-4">Recruiter Summary</h3>
        <div className="prose prose-sm max-w-none text-gray-700 whitespace-pre-wrap">
          {report.summary}
        </div>
      </div>
    </div>
  );
}
