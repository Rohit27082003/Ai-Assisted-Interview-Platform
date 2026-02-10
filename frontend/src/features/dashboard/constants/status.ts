import type { Candidate } from '../../../types';

export type StatusVariant = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

export const CANDIDATE_STATUS_VARIANT: Record<string, StatusVariant> = {
  uploaded: 'neutral',
  parsed: 'info',
  shortlisted: 'success',
  rejected: 'danger',
  focus_ready: 'warning',
  interviewing: 'info',
  interviewed: 'success',
  evaluated: 'success',
  reported: 'success',
  terminated: 'danger',
};

export const PIPELINE_STAGES = [
  'JD Intelligence',
  'Resume Parsing',
  'Shortlisting',
  'Focus Areas',
  'Interview',
  'Evaluation',
  'Report',
] as const;

export function formatCandidateStatus(status: Candidate['status']) {
  return status.replace('_', ' ');
}
