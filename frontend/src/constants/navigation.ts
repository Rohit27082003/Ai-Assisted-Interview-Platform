import { Activity, FileText, LayoutDashboard, Users } from 'lucide-react';

export interface NavigationItem {
  path: string;
  label: string;
  icon: typeof LayoutDashboard;
}

export const RECRUITER_NAV_ITEMS: NavigationItem[] = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/jd', label: 'Job Descriptions', icon: FileText },
  { path: '/candidates', label: 'Candidates', icon: Users },
  { path: '/monitor', label: 'Live Monitor', icon: Activity },
];
