import { useEffect, useState } from 'react';
import { Plus, FileText, ChevronDown, ChevronUp } from 'lucide-react';
import toast from 'react-hot-toast';
import { jdApi } from '../services/api';
import type { JobDescription } from '../types';

export default function JDPage() {
  const [jds, setJDs] = useState<JobDescription[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState('');
  const [rawText, setRawText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [expandedJD, setExpandedJD] = useState<string | null>(null);

  useEffect(() => {
    loadJDs();
  }, []);

  const loadJDs = async () => {
    try {
      const data = await jdApi.list();
      setJDs(data);
    } catch (err) {
      toast.error('Failed to load job descriptions');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !rawText.trim()) return;

    setSubmitting(true);
    try {
      const jd = await jdApi.create(title, rawText);
      setJDs([jd, ...jds]);
      setTitle('');
      setRawText('');
      setShowForm(false);
      toast.success('Job description created and parsed by AI');
    } catch (err) {
      toast.error('Failed to create job description');
    } finally {
      setSubmitting(false);
    }
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
          <h1 className="text-3xl font-bold">Job Descriptions</h1>
          <p className="mt-1 text-gray-600">
            Create JDs and let AI extract skills, competencies, and requirements
          </p>
        </div>
        <button className="btn-primary flex items-center gap-2" onClick={() => setShowForm(!showForm)}>
          <Plus className="w-5 h-5" />
          New JD
        </button>
      </div>

      {/* Create Form */}
      {showForm && (
        <form onSubmit={handleSubmit} className="card space-y-4">
          <h3 className="font-semibold text-lg">Create Job Description</h3>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Job Title</label>
            <input
              type="text"
              className="input-field"
              placeholder="e.g. Senior Backend Engineer"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Job Description Text
            </label>
            <textarea
              className="input-field min-h-[200px]"
              placeholder="Paste the full job description here..."
              value={rawText}
              onChange={(e) => setRawText(e.target.value)}
              required
            />
          </div>
          <div className="flex gap-3">
            <button type="submit" className="btn-primary" disabled={submitting}>
              {submitting ? 'Analyzing with AI...' : 'Create & Analyze'}
            </button>
            <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* JD List */}
      {jds.length === 0 ? (
        <div className="card text-center py-12">
          <FileText className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-600">No job descriptions yet</h3>
          <p className="text-gray-500 mt-1">Create your first JD to get started</p>
        </div>
      ) : (
        <div className="space-y-4">
          {jds.map((jd) => {
            const isExpanded = expandedJD === jd.jd_id;
            return (
              <div key={jd.jd_id} className="card">
                <div
                  className="flex items-center justify-between cursor-pointer"
                  onClick={() => setExpandedJD(isExpanded ? null : jd.jd_id)}
                >
                  <div>
                    <h3 className="font-semibold text-lg">{jd.title}</h3>
                    <p className="text-sm text-gray-500">
                      {new Date(jd.created_at).toLocaleDateString()} &middot;{' '}
                      {jd.must_have_skills?.length || 0} required skills
                    </p>
                  </div>
                  {isExpanded ? (
                    <ChevronUp className="w-5 h-5 text-gray-400" />
                  ) : (
                    <ChevronDown className="w-5 h-5 text-gray-400" />
                  )}
                </div>

                {isExpanded && jd.parsed_data && (
                  <div className="mt-4 pt-4 border-t space-y-4">
                    <div>
                      <h4 className="font-medium text-sm text-gray-500 mb-2">Role</h4>
                      <p>{jd.parsed_data.role}</p>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <h4 className="font-medium text-sm text-gray-500 mb-2">
                          Must-Have Skills
                        </h4>
                        <div className="flex flex-wrap gap-2">
                          {jd.must_have_skills?.map((s, i) => (
                            <span key={i} className="badge-blue">{s}</span>
                          ))}
                        </div>
                      </div>
                      <div>
                        <h4 className="font-medium text-sm text-gray-500 mb-2">
                          Nice-to-Have Skills
                        </h4>
                        <div className="flex flex-wrap gap-2">
                          {jd.good_to_have_skills?.map((s, i) => (
                            <span key={i} className="badge-gray">{s}</span>
                          ))}
                        </div>
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-4">
                      <div>
                        <h4 className="font-medium text-sm text-gray-500 mb-2">Experience</h4>
                        <p>{jd.experience_range || 'Not specified'}</p>
                      </div>
                      <div>
                        <h4 className="font-medium text-sm text-gray-500 mb-2">Tools</h4>
                        <div className="flex flex-wrap gap-2">
                          {jd.tools?.map((t, i) => (
                            <span key={i} className="badge-green">{t}</span>
                          ))}
                        </div>
                      </div>
                      <div>
                        <h4 className="font-medium text-sm text-gray-500 mb-2">Competencies</h4>
                        <div className="flex flex-wrap gap-2">
                          {jd.competencies?.map((c, i) => (
                            <span key={i} className="badge-yellow">{c}</span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
