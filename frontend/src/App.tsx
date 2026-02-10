import { Suspense, lazy } from 'react';
import { Route, Routes } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import Layout from './components/common/Layout';
import ProtectedRoute from './components/common/ProtectedRoute';
import { Loader } from './components/ui';
import { AuthProvider } from './store/AuthContext';

const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const JDPage = lazy(() => import('./pages/JDPage'));
const CandidatesPage = lazy(() => import('./pages/CandidatesPage'));
const InterviewPage = lazy(() => import('./pages/InterviewPage'));
const ReportPage = lazy(() => import('./pages/ReportPage'));
const LoginPage = lazy(() => import('./pages/LoginPage'));
const SignupPage = lazy(() => import('./pages/SignupPage'));
const ConfirmSignupPage = lazy(() => import('./pages/ConfirmSignupPage'));
const LiveMonitorPage = lazy(() => import('./pages/LiveMonitorPage'));
const TranscriptPage = lazy(() => import('./pages/TranscriptPage'));
const ResumeAnalysisPage = lazy(() => import('./pages/ResumeAnalysisPage'));
const CandidateLoginPage = lazy(() => import('./pages/candidate/CandidateLoginPage'));
const CandidatePortal = lazy(() => import('./pages/candidate/CandidatePortal'));

function RouteFallback() {
  return (
    <div className="flex h-64 items-center justify-center">
      <Loader label="Loading view" />
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          style: {
            background: '#0f172a',
            color: '#f8fafc',
            border: '1px solid rgba(148, 163, 184, 0.35)',
          },
        }}
      />

      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/confirm-signup" element={<ConfirmSignupPage />} />
          <Route path="/candidate/login" element={<CandidateLoginPage />} />
          <Route path="/candidate/portal" element={<CandidatePortal />} />
          <Route path="/candidate/interview/:interviewId" element={<InterviewPage />} />

          <Route element={<ProtectedRoute />}>
            <Route element={<Layout />}>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/jd" element={<JDPage />} />
              <Route path="/candidates" element={<CandidatesPage />} />
              <Route path="/monitor" element={<LiveMonitorPage />} />
              <Route path="/transcript/:interviewId" element={<TranscriptPage />} />
              <Route path="/report/:interviewId" element={<ReportPage />} />
              <Route path="/candidate/:candidateId/analysis" element={<ResumeAnalysisPage />} />
            </Route>
          </Route>
        </Routes>
      </Suspense>
    </AuthProvider>
  );
}
