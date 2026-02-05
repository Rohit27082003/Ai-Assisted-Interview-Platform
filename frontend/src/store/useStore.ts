import { create } from 'zustand';
import type { JobDescription, Candidate, Interview, Report } from '../types';

interface AppState {
  // JD State
  jobDescriptions: JobDescription[];
  selectedJD: JobDescription | null;
  setJobDescriptions: (jds: JobDescription[]) => void;
  setSelectedJD: (jd: JobDescription | null) => void;
  addJobDescription: (jd: JobDescription) => void;

  // Candidate State
  candidates: Candidate[];
  selectedCandidate: Candidate | null;
  setCandidates: (candidates: Candidate[]) => void;
  setSelectedCandidate: (candidate: Candidate | null) => void;
  addCandidate: (candidate: Candidate) => void;
  updateCandidate: (id: string, updates: Partial<Candidate>) => void;

  // Interview State
  activeInterview: Interview | null;
  setActiveInterview: (interview: Interview | null) => void;

  // Report State
  currentReport: Report | null;
  setCurrentReport: (report: Report | null) => void;

  // UI State
  loading: boolean;
  setLoading: (loading: boolean) => void;
}

export const useStore = create<AppState>((set) => ({
  // JD
  jobDescriptions: [],
  selectedJD: null,
  setJobDescriptions: (jds) => set({ jobDescriptions: jds }),
  setSelectedJD: (jd) => set({ selectedJD: jd }),
  addJobDescription: (jd) =>
    set((state) => ({ jobDescriptions: [jd, ...state.jobDescriptions] })),

  // Candidates
  candidates: [],
  selectedCandidate: null,
  setCandidates: (candidates) => set({ candidates }),
  setSelectedCandidate: (candidate) => set({ selectedCandidate: candidate }),
  addCandidate: (candidate) =>
    set((state) => ({ candidates: [candidate, ...state.candidates] })),
  updateCandidate: (id, updates) =>
    set((state) => ({
      candidates: state.candidates.map((c) =>
        c.candidate_id === id ? { ...c, ...updates } : c
      ),
    })),

  // Interview
  activeInterview: null,
  setActiveInterview: (interview) => set({ activeInterview: interview }),

  // Report
  currentReport: null,
  setCurrentReport: (report) => set({ currentReport: report }),

  // UI
  loading: false,
  setLoading: (loading) => set({ loading }),
}));
