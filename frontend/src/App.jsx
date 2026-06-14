import React, { Suspense, lazy, useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
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

export default function App() {
  useEffect(() => {
    initOfflineCache();
  }, []);

  return (
    <BrowserRouter>
      <LowBandwidth>
        <Navbar />
        <Suspense fallback={<LoadingFallback />}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/scan" element={<ScanPage />} />
            <Route path="/interactions" element={<InteractionChecker />} />
            <Route path="/map" element={<MapView />} />
            <Route path="/dashboard" element={<CaregiverDashboard />} />
            <Route path="/batch" element={<BatchVerification />} />
            <Route path="/report" element={<ReportForm />} />
            <Route path="/api-docs" element={<ApiDocs />} />
            <Route path="/generics" element={<GenericFinder />} />
            <Route path="/dosage" element={<DosagePage />} />
            <Route path="/side-effects" element={<SideEffectsPage />} />
            <Route path="/cabinet" element={<CabinetPage />} />
            <Route path="/prescription" element={<PrescriptionSummary />} />
            <Route path="/clinic" element={<ClinicDashboard />} />
            <Route path="/adverse-event" element={<AdverseEventReport />} />
          </Routes>
        </Suspense>
        <VoiceInterface />
      </LowBandwidth>
    </BrowserRouter>
  );
}
