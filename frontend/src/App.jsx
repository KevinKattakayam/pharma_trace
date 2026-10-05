import React, { Suspense, lazy, useEffect } from 'react';
import { BrowserRouter, Navigate, Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar';
import VoiceInterface from './components/VoiceInterface';
import LowBandwidth from './components/LowBandwidth';
import { initOfflineCache } from './utils/cache';

const Home = lazy(() => import('./pages/Home'));
const ScanPage = lazy(() => import('./pages/ScanPage'));
const InteractionChecker = lazy(() => import('./pages/InteractionChecker'));
const MapView = lazy(() => import('./pages/MapView'));
const CaregiverDashboard = lazy(() => import('./pages/CaregiverDashboard'));
const BatchVerification = lazy(() => import('./pages/BatchVerification'));
const ReportForm = lazy(() => import('./pages/ReportForm'));
const ApiDocs = lazy(() => import('./pages/ApiDocs'));
const GenericFinder = lazy(() => import('./pages/GenericFinder'));
const DosagePage = lazy(() => import('./pages/DosagePage'));
const SideEffectsPage = lazy(() => import('./pages/SideEffectsPage'));
const CabinetPage = lazy(() => import('./pages/CabinetPage'));
const PrescriptionSummary = lazy(() => import('./pages/PrescriptionSummary'));
const ClinicDashboard = lazy(() => import('./pages/ClinicDashboard'));
const AdverseEventReport = lazy(() => import('./pages/AdverseEventReport'));
const SafetyCases = lazy(() => import('./pages/SafetyCases'));
const PackCheck = lazy(() => import('./pages/PackCheck'));
const PriceCheck = lazy(() => import('./pages/PriceCheck'));

function LoadingFallback() {
  return (
    <div className="page" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
      <div style={{ textAlign: 'center' }}>
        <div className="spinner" style={{ margin: '0 auto 1rem', width: 28, height: 28 }} />
        <p style={{ color: 'var(--text-3)', fontSize: '0.8125rem' }}>Loading…</p>
      </div>
    </div>
  );
}

class AppErrorBoundary extends React.Component {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="page app-error" role="alert">
          <div className="container">
            <div className="card">
              <p className="label-text">Application error</p>
              <h1>We couldn’t load this workspace.</h1>
              <p className="legal-text">Your saved information has not been changed. Refresh to try again.</p>
              <button className="btn btn--primary" onClick={() => window.location.reload()}>Refresh application</button>
            </div>
          </div>
        </main>
      );
    }

    return this.props.children;
  }
}

const ProtectedRoute = ({ children }) => {
  const token = localStorage.getItem('pharmatrace_token');
  let isExpired = true;
  if (token) {
    try {
      const base64Url = token.split('.')[1];
      const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
      const payload = JSON.parse(window.atob(base64));
      if (payload && payload.exp && payload.exp * 1000 > Date.now()) {
        isExpired = false;
      }
    } catch (e) {
      isExpired = true;
    }
  }

  if (!token || isExpired) {
    localStorage.removeItem('pharmatrace_token');
    return <Navigate to="/" replace state={{ sessionExpired: true }} />;
  }
  return children;
};

export default function App() {
  useEffect(() => {
    initOfflineCache();
  }, []);

  return (
    <BrowserRouter>
      <AppErrorBoundary>
        <LowBandwidth>
          <Navbar />
          <Suspense fallback={<LoadingFallback />}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/scan" element={<ScanPage />} />
              <Route path="/pack-check" element={<PackCheck />} />
              <Route path="/price-check" element={<PriceCheck />} />
              <Route path="/interactions" element={<InteractionChecker />} />
              <Route path="/map" element={<MapView />} />
              <Route path="/dashboard" element={<ProtectedRoute><CaregiverDashboard /></ProtectedRoute>} />
              <Route path="/batch" element={<BatchVerification />} />
              <Route path="/report" element={<ReportForm />} />
              <Route path="/api-docs" element={<ApiDocs />} />
              <Route path="/generics" element={<GenericFinder />} />
              <Route path="/dosage" element={<DosagePage />} />
              <Route path="/side-effects" element={<SideEffectsPage />} />
              <Route path="/cabinet" element={<ProtectedRoute><CabinetPage /></ProtectedRoute>} />
              <Route path="/prescription" element={<PrescriptionSummary />} />
              <Route path="/clinic" element={<ProtectedRoute><ClinicDashboard /></ProtectedRoute>} />
              <Route path="/adverse-event" element={<AdverseEventReport />} />
              <Route path="/safety-cases" element={<ProtectedRoute><SafetyCases /></ProtectedRoute>} />
            </Routes>
          </Suspense>
          <VoiceInterface />
        </LowBandwidth>
      </AppErrorBoundary>
    </BrowserRouter>
  );
}
