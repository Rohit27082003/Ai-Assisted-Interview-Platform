import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  CheckCircle, XCircle, AlertTriangle, Award, TrendingUp,
  TrendingDown, Shield, FileText, ArrowLeft, ChevronDown, ChevronRight
} from 'lucide-react';
import toast from 'react-hot-toast';
import { evaluationApi } from '../services/api';
import type { Report, EvaluationResponse, EvaluationItem } from '../types';

export default function ReportPage() {
  const { interviewId } = useParams<{ interviewId: string }>();
  const navigate = useNavigate();
  const [report, setReport] = useState<Report | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [expandedQuestions, setExpandedQuestions] = useState<Set<number>>(new Set());

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

  const toggleQuestion = (index: number) => {
    setExpandedQuestions(prev => {
      const newSet = new Set(prev);
      if (newSet.has(index)) {
        newSet.delete(index);
      } else {
        newSet.add(index);
      }
      return newSet;
    });
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

  const getScoreColor = (score: number) => {
    if (score >= 4) return 'text-green-600';
    if (score >= 3) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getScoreBarColor = (score: number) => {
    if (score >= 4) return 'bg-green-500';
    if (score >= 3) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  const renderScoreBar = (label: string, score: number, maxScore: number = 5) => (
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium text-gray-600 w-24 shrink-0">{label}</span>
      <div className="flex-1 bg-gray-200 rounded-full h-2">
        <div
          className={`${getScoreBarColor(score)} rounded-full h-2 transition-all`}
          style={{ width: `${(score / maxScore) * 100}%` }}
        />
      </div>
      <span className={`text-xs font-bold w-8 text-right ${getScoreColor(score)}`}>
        {score.toFixed(1)}
      </span>
    </div>
  );

  const renderEvaluationCard = (ev: EvaluationItem, index: number) => {
    const isExpanded = expandedQuestions.has(index);
    return (
      <div key={index} className="border rounded-lg overflow-hidden">
        <button
          onClick={() => toggleQuestion(index)}
          className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors text-left"
        >
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <span className="text-xs font-medium text-gray-400 shrink-0">Q{index + 1}</span>
            {ev.pillar && (
              <span className="text-xs bg-primary-100 text-primary-700 px-2 py-0.5 rounded-full shrink-0">
                {ev.pillar}
              </span>
            )}
            <span className="font-medium text-sm truncate">{ev.question}</span>
          </div>
          <div className="flex items-center gap-3 shrink-0 ml-4">
            <span className={`text-lg font-bold ${getScoreColor(ev.overall_score)}`}>
              {ev.overall_score.toFixed(1)}/5
            </span>
            {isExpanded ? (
              <ChevronDown className="w-4 h-4 text-gray-400" />
            ) : (
              <ChevronRight className="w-4 h-4 text-gray-400" />
            )}
          </div>
        </button>

        {isExpanded && (
          <div className="border-t p-4 space-y-4 bg-gray-50">
            {/* Answer */}
            <div>
              <h5 className="text-xs font-semibold text-gray-500 uppercase mb-1">Candidate's Answer</h5>
              <p className="text-sm text-gray-700 bg-white p-3 rounded border">{ev.answer || 'No answer provided'}</p>
            </div>

            {/* Reference Answer */}
            <div>
              <h5 className="text-xs font-semibold text-gray-500 uppercase mb-1">Reference Answer</h5>
              <p className="text-sm text-gray-700 bg-blue-50 p-3 rounded border border-blue-100">
                {ev.reference_answer}
              </p>
            </div>

            {/* Score Dimensions */}
            <div>
              <h5 className="text-xs font-semibold text-gray-500 uppercase mb-2">Score Breakdown</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {renderScoreBar('Correctness', ev.correctness)}
                {renderScoreBar('Depth', ev.depth)}
                {renderScoreBar('Reasoning', ev.reasoning)}
                {renderScoreBar('Clarity', ev.clarity)}
                {renderScoreBar('Relevance', ev.relevance)}
                {renderScoreBar('Practical', ev.practical_application)}
              </div>
            </div>

            {/* Similarity Score */}
            {ev.similarity_score > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-gray-600">Similarity:</span>
                <div className="flex-1 bg-gray-200 rounded-full h-2 max-w-xs">
                  <div
                    className="bg-primary-500 rounded-full h-2"
                    style={{ width: `${ev.similarity_score * 100}%` }}
                  />
                </div>
                <span className="text-xs font-bold text-primary-600">
                  {(ev.similarity_score * 100).toFixed(0)}%
                </span>
              </div>
            )}

            {/* Comparison */}
            {ev.expected_vs_actual_comparison && (
              <div>
                <h5 className="text-xs font-semibold text-gray-500 uppercase mb-1">Expected vs Actual</h5>
                <p className="text-sm text-gray-700 bg-white p-3 rounded border">
                  {ev.expected_vs_actual_comparison}
                </p>
              </div>
            )}

            {/* Justification */}
            <div>
              <h5 className="text-xs font-semibold text-gray-500 uppercase mb-1">Analysis</h5>
              <p className="text-sm text-gray-600 italic">{ev.justification}</p>
            </div>
          </div>
        )}
      </div>
    );
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
              {evaluation.evaluations.map((ev, i) => renderEvaluationCard(ev, i))}
            </div>
          </div>
        )}
      </div>
    );
  }

  const rec = getRecommendationDisplay(report.recommendation);
  const RecIcon = rec.icon;

  // Extract per-question evaluation from detailed_feedback if available
  const perQuestionEval: any[] = report.detailed_feedback?.per_question_evaluation || [];

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
                      className={`${getScoreBarColor(score)} rounded-full h-2`}
                      style={{ width: `${(score / 5) * 100}%` }}
                    />
                  </div>
                  <span className={`text-sm font-bold w-8 ${getScoreColor(score)}`}>
                    {score.toFixed(1)}
                  </span>
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
            {report.cheating_flags.map((f: any, i) => (
              <li key={i} className="text-sm text-yellow-700 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                {typeof f === 'string' ? f : (
                  <span>
                    <span className="font-semibold">{f.level || 'Warning'}:</span>{' '}
                    {Array.isArray(f.reasons) ? f.reasons.join(', ') : JSON.stringify(f)}
                  </span>
                )}
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

      {/* Per-Question Evaluation Details */}
      {perQuestionEval.length > 0 && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold">Question-by-Question Evaluation</h3>
            <button
              className="text-sm text-primary-600 hover:text-primary-700"
              onClick={() => {
                if (expandedQuestions.size === perQuestionEval.length) {
                  setExpandedQuestions(new Set());
                } else {
                  setExpandedQuestions(new Set(perQuestionEval.map((_, i) => i)));
                }
              }}
            >
              {expandedQuestions.size === perQuestionEval.length ? 'Collapse All' : 'Expand All'}
            </button>
          </div>
          <div className="space-y-3">
            {perQuestionEval.map((ev: any, index: number) => {
              const isExpanded = expandedQuestions.has(index);
              const overallScore = ev.scores?.overall || ev.overall_score || 0;
              return (
                <div key={index} className="border rounded-lg overflow-hidden">
                  <button
                    onClick={() => toggleQuestion(index)}
                    className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors text-left"
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <span className="text-xs font-medium text-gray-400 shrink-0">
                        Q{ev.question_number || index + 1}
                      </span>
                      {ev.pillar && (
                        <span className="text-xs bg-primary-100 text-primary-700 px-2 py-0.5 rounded-full shrink-0">
                          {ev.pillar}
                        </span>
                      )}
                      {ev.is_follow_up && (
                        <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full shrink-0">
                          Follow-up
                        </span>
                      )}
                      <span className="font-medium text-sm truncate">{ev.question}</span>
                    </div>
                    <div className="flex items-center gap-3 shrink-0 ml-4">
                      <span className={`text-lg font-bold ${getScoreColor(overallScore)}`}>
                        {overallScore.toFixed(1)}/5
                      </span>
                      {ev.cheating_flagged && (
                        <AlertTriangle className="w-4 h-4 text-yellow-500" />
                      )}
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-gray-400" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-gray-400" />
                      )}
                    </div>
                  </button>

                  {isExpanded && (
                    <div className="border-t p-4 space-y-4 bg-gray-50">
                      {/* Answer */}
                      <div>
                        <h5 className="text-xs font-semibold text-gray-500 uppercase mb-1">
                          Candidate's Answer
                        </h5>
                        <p className="text-sm text-gray-700 bg-white p-3 rounded border">
                          {ev.answer || 'No answer provided'}
                        </p>
                      </div>

                      {/* Score Dimensions */}
                      {ev.scores && (
                        <div>
                          <h5 className="text-xs font-semibold text-gray-500 uppercase mb-2">
                            Score Breakdown
                          </h5>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                            {renderScoreBar('Correctness', ev.scores.correctness || 0)}
                            {renderScoreBar('Depth', ev.scores.depth || 0)}
                            {renderScoreBar('Reasoning', ev.scores.reasoning || 0)}
                            {renderScoreBar('Clarity', ev.scores.clarity || 0)}
                            {renderScoreBar('Relevance', ev.scores.relevance || 0)}
                            {renderScoreBar('Practical', ev.scores.practical_application || 0)}
                          </div>
                        </div>
                      )}

                      {/* Similarity Score */}
                      {ev.similarity_score > 0 && (
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-gray-600">Similarity:</span>
                          <div className="flex-1 bg-gray-200 rounded-full h-2 max-w-xs">
                            <div
                              className="bg-primary-500 rounded-full h-2"
                              style={{ width: `${ev.similarity_score * 100}%` }}
                            />
                          </div>
                          <span className="text-xs font-bold text-primary-600">
                            {(ev.similarity_score * 100).toFixed(0)}%
                          </span>
                        </div>
                      )}

                      {/* Comparison */}
                      {ev.expected_vs_actual_comparison && (
                        <div>
                          <h5 className="text-xs font-semibold text-gray-500 uppercase mb-1">
                            Expected vs Actual
                          </h5>
                          <p className="text-sm text-gray-700 bg-white p-3 rounded border">
                            {ev.expected_vs_actual_comparison}
                          </p>
                        </div>
                      )}

                      {/* Justification */}
                      {ev.justification && (
                        <div>
                          <h5 className="text-xs font-semibold text-gray-500 uppercase mb-1">Analysis</h5>
                          <p className="text-sm text-gray-600 italic">{ev.justification}</p>
                        </div>
                      )}

                      {/* Cheating Penalty */}
                      {ev.cheating_flagged && ev.cheating_penalty > 0 && (
                        <div className="bg-yellow-50 border border-yellow-200 rounded p-3">
                          <p className="text-sm text-yellow-700">
                            <AlertTriangle className="w-4 h-4 inline mr-1" />
                            Cheating penalty applied: -{ev.cheating_penalty.toFixed(1)} points
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Recruiter Insights from detailed_feedback */}
      {report.detailed_feedback?.recruiter_insights && (
        <div className="card">
          <h3 className="font-semibold mb-4">Recruiter Decision Insights</h3>
          <div className="space-y-3">
            {report.detailed_feedback.recruiter_insights.decision_factors?.map((factor: string, i: number) => (
              <div key={i} className="flex items-center gap-2 text-sm text-gray-700">
                <div className="w-1.5 h-1.5 bg-primary-500 rounded-full shrink-0" />
                {factor}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
