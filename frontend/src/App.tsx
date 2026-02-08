import { Routes, Route } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';

import { AuthProvider } from './store/AuthContext';
import Layout from './components/common/Layout';
import ProtectedRoute from './components/common/ProtectedRoute';

// Recruiter Pages
import DashboardPage from './pages/DashboardPage';
import JDPage from './pages/JDPage';
import CandidatesPage from './pages/CandidatesPage';
import InterviewPage from './pages/InterviewPage';
import ReportPage from './pages/ReportPage';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import ConfirmSignupPage from './pages/ConfirmSignupPage';
import LiveMonitorPage from './pages/LiveMonitorPage';
import TranscriptPage from './pages/TranscriptPage';
import ResumeAnalysisPage from './pages/ResumeAnalysisPage';

// Candidate Pages
import CandidateLoginPage from './pages/candidate/CandidateLoginPage';
import CandidatePortal from './pages/candidate/CandidatePortal';

export default function App() {
  return (
    <AuthProvider>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          style: {
            background: '#1e293b',
            color: '#fff',
            border: '1px solid rgba(255,255,255,0.1)',
          },
        }}
      />

      <Routes>
        {/* Public Authentication Routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/confirm-signup" element={<ConfirmSignupPage />} />
        <Route path="/candidate/login" element={<CandidateLoginPage />} />

        {/* Candidate Portal Routes (session-based auth) */}
        <Route path="/candidate/portal" element={<CandidatePortal />} />
        <Route path="/candidate/interview/:interviewId" element={<InterviewPage />} />

        {/* Protected Recruiter Routes */}
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
    </AuthProvider>
  );
}
