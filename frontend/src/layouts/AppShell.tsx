import { useState, type ReactNode } from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { BarChart3, LogOut, Menu, Mic, X } from 'lucide-react';
import { RECRUITER_NAV_ITEMS } from '../constants/navigation';
import { cn } from '../utils/cn';
import { Button } from '../components/ui';
import { useAuth } from '../store/AuthContext';

interface AppShellProps {
  children?: ReactNode;
}

export default function AppShell({ children }: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();
  const { user, logout } = useAuth();

  const handleLogout = async () => {
    await logout();
    window.location.href = '/login';
  };

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/90 backdrop-blur lg:hidden">
        <div className="flex h-14 items-center justify-between px-4">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-600 text-white">
              <Mic className="h-4 w-4" />
            </div>
            <span className="text-sm font-semibold">Interview Control</span>
          </div>
          <Button variant="ghost" size="sm" onClick={() => setSidebarOpen((prev) => !prev)}>
            {sidebarOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </Button>
        </div>
      </header>

      <div className="mx-auto flex max-w-[1600px]">
        <aside
          className={cn(
            'fixed inset-y-0 left-0 z-30 flex w-72 flex-col border-r border-slate-200 bg-white transition-transform duration-200 lg:static lg:translate-x-0',
            sidebarOpen ? 'translate-x-0' : '-translate-x-full'
          )}
        >
          <div className="border-b border-slate-200 px-5 py-6">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-600 text-white">
                <Mic className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-900">AI Interview Platform</p>
                <p className="text-xs text-slate-500">Recruiter Console</p>
              </div>
            </div>
          </div>

          <nav className="flex-1 space-y-1 p-4">
            {RECRUITER_NAV_ITEMS.map(({ path, label, icon: Icon }) => {
              const isActive = location.pathname === path;
              return (
                <Link
                  key={path}
                  to={path}
                  className={cn(
                    'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                    isActive ? 'bg-primary-50 text-primary-700' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  )}
                  onClick={() => setSidebarOpen(false)}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </Link>
              );
            })}
          </nav>

          <footer className="space-y-3 border-t border-slate-200 p-4">
            {user ? (
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <p className="truncate text-sm font-medium text-slate-800">{user.name}</p>
                <p className="truncate text-xs text-slate-500">{user.email}</p>
              </div>
            ) : null}
            <Button variant="secondary" className="w-full justify-start" onClick={handleLogout}>
              <LogOut className="h-4 w-4" />
              Logout
            </Button>
            <div className="flex items-center gap-2 px-1 text-xs text-slate-500">
              <BarChart3 className="h-3.5 w-3.5" />
              Platform v1.0.0
            </div>
          </footer>
        </aside>

        <main className="min-h-screen flex-1 px-4 py-6 lg:px-8">{children ?? <Outlet />}</main>
      </div>

      {sidebarOpen ? (
        <button
          className="fixed inset-0 z-20 bg-slate-900/30 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-label="Close sidebar"
        />
      ) : null}
    </div>
  );
}
