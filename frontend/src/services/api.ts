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

const API_BASE = '/api';

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

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

  shortlist: async (jdId: string): Promise<ShortlistResponse> => {
    const { data } = await api.post(`/candidates/${jdId}/shortlist`);
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
