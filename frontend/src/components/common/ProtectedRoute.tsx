import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { Loader } from '../ui';
import { useAuth } from '../../store/AuthContext';

interface ProtectedRouteProps {
  redirectTo?: string;
}

export default function ProtectedRoute({ redirectTo = '/login' }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader label="Checking session" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to={redirectTo} state={{ from: location }} replace />;
  }

  return <Outlet />;
}
