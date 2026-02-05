import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Plus, Upload, Filter, Play, Target, FileCheck, Users
} from 'lucide-react';
import toast from 'react-hot-toast';
import { candidateApi, jdApi, interviewApi } from '../services/api';
import type { JobDescription, Candidate, ShortlistResponse } from '../types';

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
      const result = await candidateApi.shortlist(selectedJDId);
      setShortlistResult(result);
      await loadCandidates(selectedJDId);
      toast.success(`Shortlisted ${result.shortlisted.length} candidates`);
    } catch {
      toast.error('Shortlisting failed');
    } finally {
      setActionLoading((p) => ({ ...p, shortlist: false }));
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

      {/* JD Selector */}
      <div className="card">
        <div className="flex items-center gap-4">
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
          {selectedJDId && (
            <button
              className="btn-primary flex items-center gap-2"
              onClick={handleShortlist}
              disabled={actionLoading['shortlist']}
            >
              <FileCheck className="w-4 h-4" />
              {actionLoading['shortlist'] ? 'AI Shortlisting...' : 'Run Shortlisting'}
            </button>
          )}
        </div>
      </div>

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
                  <th className="pb-3 font-medium">Name</th>
                  <th className="pb-3 font-medium">Email</th>
                  <th className="pb-3 font-medium">Score</th>
                  <th className="pb-3 font-medium">Status</th>
                  <th className="pb-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((c) => (
                  <tr key={c.candidate_id} className="border-b last:border-0">
                    <td className="py-3 font-medium">{c.name}</td>
                    <td className="py-3 text-gray-600">{c.email}</td>
                    <td className="py-3">{(c.shortlist_score * 100).toFixed(0)}%</td>
                    <td className="py-3">
                      <span className={statusColorMap[c.status] || 'badge-gray'}>
                        {c.status}
                      </span>
                    </td>
                    <td className="py-3">
                      <div className="flex gap-2">
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
                        {(c.status === 'focus_ready' || c.status === 'shortlisted') && (
                          <button
                            className="text-sm btn-primary flex items-center gap-1"
                            onClick={() => handleStartInterview(c.candidate_id)}
                            disabled={actionLoading[c.candidate_id + '_interview']}
                          >
                            <Play className="w-3 h-3" />
                            {actionLoading[c.candidate_id + '_interview']
                              ? 'Starting...'
                              : 'Interview'}
                          </button>
                        )}
                        {['interviewed', 'evaluated', 'reported'].includes(c.status) && (
                          <button
                            className="text-sm btn-secondary"
                            onClick={() => navigate(`/report/${c.candidate_id}`)}
                          >
                            View Report
                          </button>
                        )}
                      </div>
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
