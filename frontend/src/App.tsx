import { Routes, Route } from 'react-router-dom';
import Layout from './components/common/Layout';
import DashboardPage from './pages/DashboardPage';
import JDPage from './pages/JDPage';
import CandidatesPage from './pages/CandidatesPage';
import InterviewPage from './pages/InterviewPage';
import ReportPage from './pages/ReportPage';

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/jd" element={<JDPage />} />
        <Route path="/candidates" element={<CandidatesPage />} />
        <Route path="/interview/:interviewId" element={<InterviewPage />} />
        <Route path="/report/:interviewId" element={<ReportPage />} />
      </Routes>
    </Layout>
  );
}
