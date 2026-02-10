import type { Candidate, JobDescription } from '../../../types';
import { candidateApi, jdApi } from '../../../services/api';

export interface DashboardData {
  jds: JobDescription[];
  candidates: Candidate[];
}

export async function fetchDashboardData(): Promise<DashboardData> {
  const [jds, candidates] = await Promise.all([jdApi.list(), candidateApi.list()]);
  return { jds, candidates };
}
