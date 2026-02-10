import type {
  Candidate,
  EvaluationResponse,
  FocusArea,
  Interview,
  JobDescription,
  Report,
  ShortlistResponse,
} from '../types';
import { httpClient } from './http/client';

export const jdApi = {
  create: async (title: string, raw_text: string): Promise<JobDescription> => {
    const { data } = await httpClient.post('/jd/', { title, raw_text });
    return data;
  },

  list: async (): Promise<JobDescription[]> => {
    const { data } = await httpClient.get('/jd/');
    return data;
  },

  get: async (jdId: string): Promise<JobDescription> => {
    const { data } = await httpClient.get(`/jd/${jdId}`);
    return data;
  },

  delete: async (jdId: string): Promise<void> => {
    await httpClient.delete(`/jd/${jdId}`);
  },
};

export const candidateApi = {
  create: async (name: string, email: string, jd_id: string): Promise<Candidate> => {
    const { data } = await httpClient.post('/candidates/', { name, email, jd_id });
    return data;
  },

  uploadResume: async (candidateId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await httpClient.post(`/candidates/${candidateId}/upload-resume`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  shortlist: async (jdId: string, threshold = 0.65): Promise<ShortlistResponse> => {
    const { data } = await httpClient.post(`/candidates/${jdId}/shortlist?threshold=${threshold}`);
    return data;
  },

  rerunShortlist: async (jdId: string, threshold: number): Promise<ShortlistResponse> => {
    const { data } = await httpClient.post(`/candidates/${jdId}/rerun-shortlist?threshold=${threshold}`);
    return data;
  },

  generateSessions: async (jdId: string) => {
    const { data } = await httpClient.post(`/candidates/${jdId}/generate-sessions`);
    return data;
  },

  createSession: async (candidateId: string): Promise<{ session_id: string }> => {
    const { data } = await httpClient.post(`/candidates/${candidateId}/session`);
    return data;
  },

  generateFocusAreas: async (candidateId: string): Promise<{ candidate_id: string; focus_areas: FocusArea[] }> => {
    const { data } = await httpClient.post(`/candidates/${candidateId}/focus-areas`);
    return data;
  },

  list: async (jdId?: string): Promise<Candidate[]> => {
    const params = jdId ? { jd_id: jdId } : {};
    const { data } = await httpClient.get('/candidates/', { params });
    return data;
  },

  get: async (candidateId: string): Promise<Candidate> => {
    const { data } = await httpClient.get(`/candidates/${candidateId}`);
    return data;
  },

  getResumeUrl: async (candidateId: string): Promise<{ download_url: string }> => {
    const { data } = await httpClient.get(`/candidates/${candidateId}/resume`);
    return data;
  },

  delete: async (candidateId: string): Promise<void> => {
    await httpClient.delete(`/candidates/${candidateId}`);
  },
};

export const interviewApi = {
  start: async (candidateId: string): Promise<Interview> => {
    const { data } = await httpClient.post('/interviews/start', { candidate_id: candidateId });
    return data;
  },

  get: async (interviewId: string): Promise<Interview> => {
    const { data } = await httpClient.get(`/interviews/${interviewId}`);
    return data;
  },

  getProgress: async (interviewId: string) => {
    const { data } = await httpClient.get(`/interviews/${interviewId}/progress`);
    return data;
  },

  getMonitorActive: async (): Promise<
    Array<{
      interview_id: string;
      candidate_name: string;
      candidate_email: string;
      current_pillar: string;
      question_number: number;
      status: string;
    }>
  > => {
    const { data } = await httpClient.get('/interviews/monitor/active');
    return data;
  },

  terminate: async (interviewId: string): Promise<void> => {
    await httpClient.post(`/interviews/${interviewId}/terminate`);
  },
};

export const evaluationApi = {
  evaluate: async (interviewId: string): Promise<EvaluationResponse> => {
    const { data } = await httpClient.post(`/evaluations/${interviewId}/evaluate`);
    return data;
  },

  generateReport: async (interviewId: string): Promise<Report> => {
    const { data } = await httpClient.post(`/evaluations/${interviewId}/report`);
    return data;
  },

  getReport: async (interviewId: string): Promise<Report> => {
    const { data } = await httpClient.get(`/evaluations/${interviewId}/report`);
    return data;
  },
};
