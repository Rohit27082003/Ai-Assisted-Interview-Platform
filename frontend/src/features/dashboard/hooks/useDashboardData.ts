import { useCallback, useEffect, useState } from 'react';
import type { Candidate, JobDescription } from '../../../types';
import { fetchDashboardData } from '../services/dashboardService';

interface DashboardState {
  jds: JobDescription[];
  candidates: Candidate[];
  isLoading: boolean;
  error: string | null;
}

const initialState: DashboardState = {
  jds: [],
  candidates: [],
  isLoading: true,
  error: null,
};

export function useDashboardData() {
  const [state, setState] = useState<DashboardState>(initialState);

  const loadData = useCallback(async () => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const data = await fetchDashboardData();
      setState({ ...data, isLoading: false, error: null });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to load dashboard data.';
      setState((prev) => ({ ...prev, isLoading: false, error: message }));
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  return {
    ...state,
    reload: loadData,
  };
}
