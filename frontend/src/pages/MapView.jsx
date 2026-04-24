import React, { useState, useEffect, useRef } from 'react';
import PharmacyCard from '../components/PharmacyCard';
import api from '../utils/api';

export default function MapView() {
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const [reports, setReports] = useState([]);
  const [pharmacies, setPharmacies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('heatmap');

  useEffect(() => {
    let mounted = true;

    async function loadMap() {
      const L = await import('leaflet');
      await import('leaflet/dist/leaflet.css');

      if (!mounted || !mapRef.current || mapInstanceRef.current) return;

      const map = L.map(mapRef.current, { zoomControl: false, scrollWheelZoom: false }).setView([20, 78], 5);

      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; CARTO', maxZoom: 19
      }).addTo(map);

      L.control.zoom({ position: 'bottomright' }).addTo(map);
      mapInstanceRef.current = map;

      try {
        const [heatmapData, pharmacyData] = await Promise.all([
          api.getHeatmapData(),
          api.getNearbyPharmacies(20, 78)
        ]);

        if (mounted) {
          const rList = heatmapData.reports || [];
          const pList = pharmacyData.pharmacies || [];
          setReports(rList);
          setPharmacies(pList);
          setLoading(false);

          // Custom Marker Icons Logic (Simplified for CSS-based markers)
          rList.forEach(r => {
            if (r.lat == null || r.lng == null) return;
            const marker = L.divIcon({
              className: 'custom-pulse-marker',
              html: `<div class="pulse-marker pulse-marker--danger"></div>`,
              iconSize: [20, 20]
            });
            L.marker([r.lat, r.lng], { icon: marker }).addTo(map).bindPopup(`
              <div class="map-popup">
                <div class="map-popup__tag">Vigilance Alert</div>
                <div class="map-popup__title">${r.drug_name || 'Pharmacological Query'}</div>
                <div class="map-popup__content">
                  Status: <span style="color:var(--danger)">Suspicious Activity</span><br/>
                  Location: ${r.city || 'Undisclosed Area'}
                </div>
              </div>
            `);
          });

          pList.forEach(p => {
            if (p.lat == null || p.lng == null) return;
            const colorClass = p.trust_score >= 70 ? 'safe' : p.trust_score >= 40 ? 'warn' : 'danger';
            const marker = L.divIcon({
              className: 'custom-pharmacy-marker',
              html: `<div class="pharmacy-marker pharmacy-marker--${colorClass}"></div>`,
              iconSize: [24, 24]
            });
            L.marker([p.lat, p.lng], { icon: marker }).addTo(map).bindPopup(`
              <div class="map-popup">
                <div class="map-popup__tag map-popup__tag--${colorClass}">Pharmacy Entity</div>
                <div class="map-popup__title">${p.name}</div>
                <div class="map-popup__content">
                  Trust Index: <span style="color:var(--${colorClass})">${p.trust_score}/100</span><br/>
                  ${p.address || ''}
                </div>
              </div>
            `);
          });

          const allPoints = [
            ...rList.filter(r => r.lat && r.lng).map(r => [r.lat, r.lng]),
            ...pList.filter(p => p.lat && p.lng).map(p => [p.lat, p.lng])
          ];
          if (allPoints.length > 0) {
            map.fitBounds(L.latLngBounds(allPoints).pad(0.2));
          }
        }
      } catch (err) {
        if (mounted) { setError(err.message); setLoading(false); }
      }
    }

    loadMap();
    return () => { 
      mounted = false; 
      if (mapInstanceRef.current) { 
        mapInstanceRef.current.remove(); 
        mapInstanceRef.current = null; 
      } 
    };
  }, []);

  return (
    <div className="page" style={{ paddingBottom: 0 }}>
      {/* Dashboard Top Navigation */}
      <div className="container" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: '1.5rem', flexWrap: 'wrap' }} className="anim">
          <div>
            <div className="hero__tag" style={{ marginBottom: '0.6rem' }}>
              <span className="hero__tag-dot" /> Live Monitoring Active
            </div>
            <h1 style={{ fontSize: '2.5rem', fontWeight: 900, letterSpacing: '-0.04em', lineHeight: 1 }}>Geospatial Intel</h1>
            <p style={{ color: 'var(--text-3)', fontSize: '0.9375rem', marginTop: '0.5rem', maxWidth: '500px' }}>
              Real-time visualization of supply chain integrity, registered pharmacies, and reported counterfeit clusters across the subcontinent.
            </p>
          </div>
          
          <div style={{ display: 'flex', background: 'var(--bg-tertiary)', padding: '4px', borderRadius: '12px', border: '1px solid var(--border-1)' }}>
            {[
              { id: 'heatmap', label: 'Threat Clusters' },
              { id: 'pharmacies', label: 'Verified Network' }
            ].map(t => (
              <button key={t.id} onClick={() => setActiveTab(t.id)}
                style={{
                  padding: '0.6rem 1.25rem', borderRadius: '9px', fontSize: '0.8125rem', fontWeight: 700,
                  background: activeTab === t.id ? 'var(--accent)' : 'transparent',
                  color: activeTab === t.id ? '#fff' : 'var(--text-3)',
                  transition: 'all 0.2s var(--ease)'
                }}>
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 280px)', minHeight: '600px', gap: '1rem', padding: '0 1rem' }}>
         <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '1rem', height: '100%', flex: 1 }}>
            {/* Map Core */}
            <div className="map-container anim" style={{ height: '100%', borderRadius: '24px', overflow: 'hidden', border: '1px solid var(--border-1)', position: 'relative' }}>
               <div ref={mapRef} style={{ height: '100%', width: '100%', background: '#0a0a0c' }} />
               {loading && (
                 <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, flexDirection: 'column', gap: '1rem' }}>
                   <div className="spinner" />
                   <div style={{ fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--accent)' }}>Decoding Terrain Data...</div>
                 </div>
               )}
            </div>

            {/* Side Intelligence Panel */}
            <div className="anim anim-d1" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
               <div className="card" style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '1.5rem' }}>
                  <h3 style={{ fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-3)', marginBottom: '1.25rem' }}>Global Analytics</h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                    {[
                      { label: 'Active Alerts', val: reports.length, color: 'var(--danger)', trend: '+12%' },
                      { label: 'Network Entities', val: pharmacies.length, color: 'var(--accent)', trend: '+3 ago' },
                      { label: 'Security Score', val: '98.2', color: 'var(--safe)', trend: 'STABLE' },
                    ].map((s, i) => (
                      <div key={i}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '0.4rem' }}>
                           <span style={{ fontSize: '1.75rem', fontWeight: 900, fontFamily: 'var(--mono)', color: s.color }}>{s.val}</span>
                           <span style={{ fontSize: '0.625rem', fontWeight: 800, color: 'var(--text-3)', paddingBottom: '0.25rem' }}>{s.trend}</span>
                        </div>
                        <div style={{ fontSize: '0.6875rem', fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{s.label}</div>
                      </div>
                    ))}
                  </div>

                  <div style={{ marginTop: 'auto', borderTop: '1px solid var(--border-1)', paddingTop: '1.25rem' }}>
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-3)', lineHeight: 1.5 }}>
                      Satellite data filtered through PharmaTrace Trust Layer. Verified entities are updated every 6 hours.
                    </p>
                  </div>
               </div>
            </div>
         </div>

         {/* Bottom Detail List (Only visible when Pharmacies tab is on) */}
         {activeTab === 'pharmacies' && pharmacies.length > 0 && (
           <div className="anim anim-up" style={{ padding: '0.5rem 0' }}>
             <div style={{ display: 'flex', gap: '1rem', overflowX: 'auto', paddingBottom: '1rem' }} className="no-scrollbar">
               {pharmacies.map((p, i) => (
                 <div key={i} style={{ minWidth: '320px' }}>
                    <PharmacyCard pharmacy={p} />
                 </div>
               ))}
             </div>
           </div>
         )}
      </div>
    </div>
  );
}

