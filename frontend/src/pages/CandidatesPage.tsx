import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Plus, Upload, Filter, Play, Target, FileCheck, Users, Key, RefreshCw, Sliders, Copy, FileText, Trash2, ChevronDown, ChevronRight, Eye, BarChart2
} from 'lucide-react';
import toast from 'react-hot-toast';
import { candidateApi, jdApi, interviewApi } from '../services/api';
import type { JobDescription, Candidate, ShortlistResponse, FocusArea } from '../types';

interface CandidateSession {
  candidate_id: string;
  name: string;
  email: string;
  session_id: string;
  session_expires_at: string;
}

export default function CandidatesPage() {
  const navigate = useNavigate();
  const [jds, setJDs] = useState<JobDescription[]>([]);
  const [selectedJDId, setSelectedJDId] = useState('');
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [shortlistResult, setShortlistResult] = useState<ShortlistResponse | null>(null);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});

  // New state for threshold and sessions
  const [threshold, setThreshold] = useState(0.65);
  const [showSessions, setShowSessions] = useState(false);
  const [sessions, setSessions] = useState<CandidateSession[]>([]);
  const [expandedCandidates, setExpandedCandidates] = useState<Set<string>>(new Set());

  const toggleExpandCandidate = (candidateId: string) => {
    setExpandedCandidates(prev => {
      const newSet = new Set(prev);
      if (newSet.has(candidateId)) {
        newSet.delete(candidateId);
      } else {
        newSet.add(candidateId);
      }
      return newSet;
    });
  };

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (selectedJDId) {
      loadCandidates(selectedJDId);
    }
  }, [selectedJDId]);

  const loadData = async () => {
    try {
      const jdList = await jdApi.list();
      setJDs(jdList);
      if (jdList.length > 0) {
        setSelectedJDId(jdList[0].jd_id);
      }
    } catch {
      toast.error('Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  const loadCandidates = async (jdId: string) => {
    try {
      const data = await candidateApi.list(jdId);
      setCandidates(data);
    } catch {
      toast.error('Failed to load candidates');
    }
  };

  const handleCreateCandidate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name || !email || !selectedJDId) return;

    setSubmitting(true);
    try {
      const candidate = await candidateApi.create(name, email, selectedJDId);

      if (resumeFile) {
        await candidateApi.uploadResume(candidate.candidate_id, resumeFile);
        toast.success('Candidate created and resume uploaded');
      } else {
        toast.success('Candidate created');
      }

      setName('');
      setEmail('');
      setResumeFile(null);
      setShowForm(false);
      await loadCandidates(selectedJDId);
    } catch {
      toast.error('Failed to create candidate');
    } finally {
      setSubmitting(false);
    }
  };

  const handleShortlist = async () => {
    if (!selectedJDId) return;
    setActionLoading((p) => ({ ...p, shortlist: true }));
    try {
      const result = await candidateApi.shortlist(selectedJDId, threshold);
      setShortlistResult(result);
      await loadCandidates(selectedJDId);
      toast.success(`Shortlisted ${result.shortlisted.length} candidates (threshold: ${(threshold * 100).toFixed(0)}%)`);
    } catch {
      toast.error('Shortlisting failed');
    } finally {
      setActionLoading((p) => ({ ...p, shortlist: false }));
    }
  };

  const handleRerunShortlist = async () => {
    if (!selectedJDId) return;
    setActionLoading((p) => ({ ...p, rerun: true }));
    try {
      const result = await candidateApi.rerunShortlist(selectedJDId, threshold);
      setShortlistResult(result);
      await loadCandidates(selectedJDId);
      toast.success(`Re-shortlisted with threshold ${(threshold * 100).toFixed(0)}%: ${result.shortlisted.length} shortlisted`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Re-shortlisting failed';
      toast.error(message);
    } finally {
      setActionLoading((p) => ({ ...p, rerun: false }));
    }
  };

  const handleGenerateSessions = async () => {
    if (!selectedJDId) return;
    setActionLoading((p) => ({ ...p, sessions: true }));
    try {
      const result = await candidateApi.generateSessions(selectedJDId);
      setSessions(result.sessions);
      setShowSessions(true);
      toast.success(`Generated ${result.total_generated} session IDs`);
    } catch {
      toast.error('Failed to generate sessions');
    } finally {
      setActionLoading((p) => ({ ...p, sessions: false }));
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success('Copied to clipboard!');
  };

  const handleDeleteCandidate = async (candidateId: string) => {
    if (!window.confirm('Are you sure you want to delete this candidate?')) return;

    setActionLoading((p) => ({ ...p, [candidateId + '_delete']: true }));
    try {
      await candidateApi.delete(candidateId);
      toast.success('Candidate deleted');
      await loadCandidates(selectedJDId);
    } catch {
      toast.error('Failed to delete candidate');
    } finally {
      setActionLoading((p) => ({ ...p, [candidateId + '_delete']: false }));
    }
  };

  const handleFocusAreas = async (candidateId: string) => {
    setActionLoading((p) => ({ ...p, [candidateId + '_focus']: true }));
    try {
      const result = await candidateApi.generateFocusAreas(candidateId);
      toast.success(`${result.focus_areas.length} focus areas generated`);
      await loadCandidates(selectedJDId);
    } catch {
      toast.error('Failed to generate focus areas');
    } finally {
      setActionLoading((p) => ({ ...p, [candidateId + '_focus']: false }));
    }
  };

  const handleStartInterview = async (candidateId: string) => {
    setActionLoading((p) => ({ ...p, [candidateId + '_interview']: true }));
    try {
      const interview = await interviewApi.start(candidateId);
      toast.success('Interview started');
      navigate(`/interview/${interview.interview_id}`);
    } catch {
      toast.error('Failed to start interview');
    } finally {
      setActionLoading((p) => ({ ...p, [candidateId + '_interview']: false }));
    }
  };

  const statusColorMap: Record<string, string> = {
    uploaded: 'badge-gray',
    parsed: 'badge-blue',
    shortlisted: 'badge-green',
    rejected: 'badge-red',
    focus_ready: 'badge-yellow',
    interviewing: 'badge-blue',
    interviewed: 'badge-green',
    evaluated: 'badge-green',
    reported: 'badge-green',
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Candidates</h1>
          <p className="mt-1 text-gray-600">Manage candidates through the AI interview pipeline</p>
        </div>
        <div className="flex gap-3">
          <button
            className="btn-primary flex items-center gap-2"
            onClick={() => setShowForm(!showForm)}
          >
            <Plus className="w-5 h-5" /> Add Candidate
          </button>
        </div>
      </div>

      {/* JD Selector & Threshold Controls */}
      <div className="card space-y-4">
        <div className="flex items-center gap-4 flex-wrap">
          <Filter className="w-5 h-5 text-gray-400" />
          <select
            className="input-field max-w-md"
            value={selectedJDId}
            onChange={(e) => setSelectedJDId(e.target.value)}
          >
            <option value="">Select Job Description</option>
            {jds.map((jd) => (
              <option key={jd.jd_id} value={jd.jd_id}>
                {jd.title}
              </option>
            ))}
          </select>
        </div>

        {selectedJDId && (
          <>
            {/* Threshold Slider */}
            <div className="flex items-center gap-4 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
              <Sliders className="w-5 h-5 text-primary-600" />
              <div className="flex-1">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Shortlisting Threshold
                  </label>
                  <span className="text-lg font-bold text-primary-600">
                    {(threshold * 100).toFixed(0)}%
                  </span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={threshold * 100}
                  onChange={(e) => setThreshold(Number(e.target.value) / 100)}
                  className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary-600"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>More candidates</span>
                  <span>Higher quality</span>
                </div>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3 flex-wrap">
              <button
                className="btn-primary flex items-center gap-2"
                onClick={handleShortlist}
                disabled={actionLoading['shortlist']}
              >
                <FileCheck className="w-4 h-4" />
                {actionLoading['shortlist'] ? 'AI Shortlisting...' : 'Run Shortlisting'}
              </button>

              <button
                className="btn-secondary flex items-center gap-2"
                onClick={handleRerunShortlist}
                disabled={actionLoading['rerun']}
              >
                <RefreshCw className="w-4 h-4" />
                {actionLoading['rerun'] ? 'Re-evaluating...' : 'Re-run with New Threshold'}
              </button>

              <button
                className="btn-secondary flex items-center gap-2 ml-auto"
                onClick={handleGenerateSessions}
                disabled={actionLoading['sessions']}
              >
                <Key className="w-4 h-4" />
                {actionLoading['sessions'] ? 'Generating...' : 'Generate Session IDs'}
              </button>
            </div>
          </>
        )}
      </div>

      {/* Session IDs Modal/Section */}
      {showSessions && sessions.length > 0 && (
        <div className="card border-2 border-primary-200 dark:border-primary-800">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-lg flex items-center gap-2">
              <Key className="w-5 h-5 text-primary-600" />
              Candidate Session IDs
            </h3>
            <button
              onClick={() => setShowSessions(false)}
              className="text-gray-500 hover:text-gray-700"
            >
              ✕
            </button>
          </div>
          <p className="text-sm text-gray-600 mb-4">
            Share these session IDs with candidates so they can log in to their interview portal.
          </p>
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {sessions.map((s) => (
              <div
                key={s.candidate_id}
                className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-lg"
              >
                <div>
                  <p className="font-medium">{s.name}</p>
                  <p className="text-sm text-gray-500">{s.email}</p>
                </div>
                <div className="flex items-center gap-2">
                  <code className="px-2 py-1 bg-gray-200 dark:bg-gray-700 rounded text-xs font-mono">
                    {s.session_id.substring(0, 12)}...
                  </code>
                  <button
                    onClick={() => copyToClipboard(s.session_id)}
                    className="p-2 hover:bg-gray-200 dark:hover:bg-gray-700 rounded"
                    title="Copy session ID"
                  >
                    <Copy className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Add Candidate Form */}
      {showForm && (
        <form onSubmit={handleCreateCandidate} className="card space-y-4">
          <h3 className="font-semibold text-lg">Add New Candidate</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                type="text"
                className="input-field"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input
                type="email"
                className="input-field"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Resume</label>
            <div className="flex items-center gap-4">
              <label className="btn-secondary cursor-pointer flex items-center gap-2">
                <Upload className="w-4 h-4" />
                {resumeFile ? resumeFile.name : 'Choose File'}
                <input
                  type="file"
                  className="hidden"
                  accept=".pdf,.docx,.doc,.txt"
                  onChange={(e) => setResumeFile(e.target.files?.[0] || null)}
                />
              </label>
            </div>
          </div>
          <div className="flex gap-3">
            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting ? 'Creating...' : 'Create Candidate'}
            </button>
            <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Shortlist Results */}
      {shortlistResult && (
        <div className="card bg-green-50 border-green-200">
          <h3 className="font-semibold text-green-800 mb-2">
            Shortlisting Complete
          </h3>
          <p className="text-green-700">
            {shortlistResult.shortlisted.length} shortlisted,{' '}
            {shortlistResult.rejected.length} rejected out of{' '}
            {shortlistResult.total_candidates} candidates
          </p>
        </div>
      )}

      {/* Candidates Table */}
      <div className="card">
        <div className="flex items-center gap-3 mb-4">
          <Users className="w-5 h-5 text-gray-400" />
          <h3 className="font-semibold text-lg">Candidates ({candidates.length})</h3>
        </div>

        {candidates.length === 0 ? (
          <p className="text-gray-500 py-8 text-center">
            No candidates for this JD yet
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-sm text-gray-500 border-b">
                  <th className="pb-3 font-medium w-8"></th>
                  <th className="pb-3 font-medium">Name</th>
                  <th className="pb-3 font-medium">Email</th>
                  <th className="pb-3 font-medium">Match Score</th>
                  <th className="pb-3 font-medium">Status</th>
                  <th className="pb-3 font-medium">Focus Areas</th>
                  <th className="pb-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((c) => {
                  const hasFocusAreas = c.focus_areas && c.focus_areas.length > 0;
                  const isExpanded = expandedCandidates.has(c.candidate_id);

                  return (
                    <React.Fragment key={c.candidate_id}>
                      <tr className="border-b last:border-0">
                        <td className="py-3">
                          {hasFocusAreas && (
                            <button
                              onClick={() => toggleExpandCandidate(c.candidate_id)}
                              className="p-1 hover:bg-gray-100 rounded"
                            >
                              {isExpanded ? (
                                <ChevronDown className="w-4 h-4 text-gray-500" />
                              ) : (
                                <ChevronRight className="w-4 h-4 text-gray-500" />
                              )}
                            </button>
                          )}
                        </td>
                        <td className="py-3 font-medium">{c.name}</td>
                        <td className="py-3 text-gray-600">{c.email}</td>
                        <td className="py-3">
                          <div className="flex flex-col">
                            <span className="font-bold text-lg">{(c.shortlist_score * 100).toFixed(0)}%</span>
                            {c.scoring_analysis?.reasoning && (
                              <span
                                className="text-xs text-gray-500 mt-1 max-w-[200px] truncate block"
                                title={c.scoring_analysis.reasoning}
                              >
                                {c.scoring_analysis.reasoning}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-3">
                          <span className={statusColorMap[c.status] || 'badge-gray'}>
                            {c.status}
                          </span>
                        </td>
                        <td className="py-3">
                          {hasFocusAreas ? (
                            <button
                              onClick={() => toggleExpandCandidate(c.candidate_id)}
                              className="text-sm text-primary-600 hover:text-primary-700 flex items-center gap-1"
                            >
                              <Eye className="w-3 h-3" />
                              {c.focus_areas.length} topics
                            </button>
                          ) : c.status === 'shortlisted' ? (
                            <span className="text-xs text-gray-400">Not generated</span>
                          ) : (
                            <span className="text-xs text-gray-400">-</span>
                          )}
                        </td>
                        <td className="py-3">
                          <div className="flex gap-2">
                            {/* Analysis Button */}
                            <button
                              className="text-sm btn-secondary flex items-center gap-1 text-primary-600"
                              onClick={() => navigate(`/candidate/${c.candidate_id}/analysis`)}
                              title="View Analysis"
                            >
                              <BarChart2 className="w-3 h-3" />
                              Analysis
                            </button>

                            {/* View Resume button */}
                            <button
                              className="text-sm btn-secondary flex items-center gap-1"
                              onClick={async () => {
                                try {
                                  const result = await candidateApi.getResumeUrl(c.candidate_id);
                                  window.open(result.download_url, '_blank');
                                } catch {
                                  toast.error('Resume not available');
                                }
                              }}
                              title="View Resume"
                            >
                              <FileText className="w-3 h-3" />
                              Resume
                            </button>
                            {c.status === 'shortlisted' && (
                              <button
                                className="text-sm btn-secondary flex items-center gap-1"
                                onClick={() => handleFocusAreas(c.candidate_id)}
                                disabled={actionLoading[c.candidate_id + '_focus']}
                              >
                                <Target className="w-3 h-3" />
                                {actionLoading[c.candidate_id + '_focus']
                                  ? 'Generating...'
                                  : 'Focus Areas'}
                              </button>
                            )}
                            {/* Interview button removed for recruiters */}
                            {['interviewed', 'evaluated', 'reported'].includes(c.status) && (
                              <button
                                className="text-sm btn-secondary"
                                onClick={() => navigate(`/report/${c.interview_id}`)}
                              >
                                View Report
                              </button>
                            )}
                            {c.interview_id && (
                              <button
                                className="text-sm btn-secondary flex items-center gap-1"
                                onClick={() => navigate(`/transcript/${c.interview_id}`)}
                                title="View Transcript"
                              >
                                <FileText className="w-3 h-3" />
                                Transcript
                              </button>
                            )}
                            <button
                              className="text-sm btn-secondary text-red-600 hover:text-red-700 hover:bg-red-50"
                              onClick={() => handleDeleteCandidate(c.candidate_id)}
                              disabled={actionLoading[c.candidate_id + '_delete']}
                              title="Delete Candidate"
                            >
                              <Trash2 className="w-3 h-3" />
                            </button>
                          </div>
                        </td>
                      </tr>
                      {/* Expanded Focus Areas Row */}
                      {hasFocusAreas && isExpanded && (
                        <tr className="bg-gray-50 dark:bg-gray-800">
                          <td colSpan={7} className="py-4 px-6">
                            <div className="ml-8">
                              <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
                                <Target className="w-4 h-4 text-primary-600" />
                                Interview Focus Areas for {c.name}
                              </h4>
                              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                {c.focus_areas.map((fa: FocusArea, idx: number) => (
                                  <div
                                    key={idx}
                                    className="bg-white dark:bg-gray-700 p-3 rounded-lg border border-gray-200 dark:border-gray-600"
                                  >
                                    <div className="font-medium text-primary-600 dark:text-primary-400 mb-1">
                                      {fa.skill}
                                    </div>
                                    <p className="text-xs text-gray-600 dark:text-gray-400">
                                      {fa.reason}
                                    </p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div >
  );
}
