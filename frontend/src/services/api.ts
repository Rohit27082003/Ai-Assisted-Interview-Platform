import axios from 'axios';
import type {
  JobDescription,
  Candidate,
  ShortlistResponse,
  FocusArea,
  Interview,
  EvaluationResponse,
  Report,
} from '../types';
import { getAuthHeader } from '../store/AuthContext';

const API_BASE = '/api';

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

// Add auth header interceptor
api.interceptors.request.use((config) => {
  const authHeader = getAuthHeader();
  if (authHeader.Authorization) {
    config.headers.Authorization = authHeader.Authorization;
  }
  return config;
});

// Add response interceptor for auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Dispatch global event for auth failure
      window.dispatchEvent(new Event('auth:unauthorized'));
    }
    return Promise.reject(error);
  }
);

// ── Job Descriptions ─────────────────────────────────────────

export const jdApi = {
  create: async (title: string, raw_text: string): Promise<JobDescription> => {
    const { data } = await api.post('/jd/', { title, raw_text });
    return data;
  },

  list: async (): Promise<JobDescription[]> => {
    const { data } = await api.get('/jd/');
    return data;
  },

  get: async (jdId: string): Promise<JobDescription> => {
    const { data } = await api.get(`/jd/${jdId}`);
    return data;
  },

  delete: async (jdId: string): Promise<void> => {
    await api.delete(`/jd/${jdId}`);
  },
};

// ── Candidates ───────────────────────────────────────────────

export const candidateApi = {
  create: async (name: string, email: string, jd_id: string): Promise<Candidate> => {
    const { data } = await api.post('/candidates/', { name, email, jd_id });
    return data;
  },

  uploadResume: async (candidateId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await api.post(
      `/candidates/${candidateId}/upload-resume`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
    return data;
  },

  shortlist: async (jdId: string, threshold: number = 0.65): Promise<ShortlistResponse> => {
    const { data } = await api.post(`/candidates/${jdId}/shortlist?threshold=${threshold}`);
    return data;
  },

  rerunShortlist: async (jdId: string, threshold: number): Promise<ShortlistResponse> => {
    const { data } = await api.post(`/candidates/${jdId}/rerun-shortlist?threshold=${threshold}`);
    return data;
  },

  generateSessions: async (jdId: string) => {
    const { data } = await api.post(`/candidates/${jdId}/generate-sessions`);
    return data;
  },

  generateFocusAreas: async (candidateId: string): Promise<{ candidate_id: string; focus_areas: FocusArea[] }> => {
    const { data } = await api.post(`/candidates/${candidateId}/focus-areas`);
    return data;
  },

  list: async (jdId?: string): Promise<Candidate[]> => {
    const params = jdId ? { jd_id: jdId } : {};
    const { data } = await api.get('/candidates/', { params });
    return data;
  },

  get: async (candidateId: string): Promise<Candidate> => {
    const { data } = await api.get(`/candidates/${candidateId}`);
    return data;
  },

  getResumeUrl: async (candidateId: string): Promise<{ download_url: string }> => {
    const { data } = await api.get(`/candidates/${candidateId}/resume`);
    return data;
  },

  delete: async (candidateId: string): Promise<void> => {
    await api.delete(`/candidates/${candidateId}`);
  },
};

// ── Interviews ───────────────────────────────────────────────

export const interviewApi = {
  start: async (candidateId: string): Promise<Interview> => {
    const { data } = await api.post('/interviews/start', { candidate_id: candidateId });
    return data;
  },

  get: async (interviewId: string): Promise<Interview> => {
    const { data } = await api.get(`/interviews/${interviewId}`);
    return data;
  },

  getProgress: async (interviewId: string) => {
    const { data } = await api.get(`/interviews/${interviewId}/progress`);
    return data;
  },

  getMonitorActive: async (): Promise<Array<{
    interview_id: string;
    candidate_name: string;
    candidate_email: string;
    current_pillar: string;
    question_number: number;
    status: string;
  }>> => {
    const { data } = await api.get('/interviews/monitor/active');
    return data;
  },

  terminate: async (interviewId: string): Promise<void> => {
    await api.post(`/interviews/${interviewId}/terminate`);
  },
};

// ── Evaluations & Reports ────────────────────────────────────

export const evaluationApi = {
  evaluate: async (interviewId: string): Promise<EvaluationResponse> => {
    const { data } = await api.post(`/evaluations/${interviewId}/evaluate`);
    return data;
  },

  generateReport: async (interviewId: string): Promise<Report> => {
    const { data } = await api.post(`/evaluations/${interviewId}/report`);
    return data;
  },

  getReport: async (interviewId: string): Promise<Report> => {
    const { data } = await api.get(`/evaluations/${interviewId}/report`);
    return data;
  },
};
