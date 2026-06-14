import React, { useState, useEffect, useRef } from 'react';
import PharmacyCard from '../components/PharmacyCard';
import api from '../utils/api';

export default function MapView() {
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const markersGroupRef = useRef(null);
  const [reports, setReports] = useState([]);
  const [pharmacies, setPharmacies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('heatmap');
  const [timeFilterDays, setTimeFilterDays] = useState(30);
  const [activeCluster, setActiveCluster] = useState(null);

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
      markersGroupRef.current = L.layerGroup().addTo(map);

      try {
        const [heatmapData, pharmacyData] = await Promise.all([
          api.getHeatmapData(),
          api.getNearbyPharmacies(20, 78)
        ]);

        if (mounted) {
          setReports(heatmapData.reports || []);
          setPharmacies(pharmacyData.pharmacies || []);
          setLoading(false);
          
          const pList = pharmacyData.pharmacies || [];
          const allPoints = pList.filter(p => p.lat && p.lng).map(p => [p.lat, p.lng]);
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

  useEffect(() => {
    if (!mapInstanceRef.current || !markersGroupRef.current) return;
    const L = window.L;
    const layerGroup = markersGroupRef.current;
    layerGroup.clearLayers();

    if (activeTab === 'heatmap') {
      const now = new Date();
      
      // Filter and cluster reports
      const clusters = {};
      reports.forEach(r => {
         if (r.lat == null || r.lng == null) return;
         const reportedAt = r.reported_at ? new Date(r.reported_at) : new Date();
         const daysSince = (now - reportedAt) / (1000 * 60 * 60 * 24);
         
         if (daysSince > timeFilterDays) return;
         
         const key = `${r.lat.toFixed(1)},${r.lng.toFixed(1)}`;
         if (!clusters[key]) clusters[key] = { lat: r.lat, lng: r.lng, reports: [], minDays: daysSince };
         clusters[key].reports.push(r);
         clusters[key].minDays = Math.min(clusters[key].minDays, daysSince);
      });

      Object.values(clusters).forEach(cluster => {
        // Exponential decay for opacity based on recency (half-life of 14 days)
        const decay = Math.exp(-0.05 * cluster.minDays);
        const opacity = Math.max(0.15, decay);
        const scale = 1 + (cluster.reports.length * 0.1);

        const marker = L.divIcon({
          className: 'custom-pulse-marker',
          html: `<div class="pulse-marker pulse-marker--danger" style="opacity: ${opacity}; transform: scale(${Math.min(scale, 3)})"></div>`,
          iconSize: [20, 20]
        });
        
        const m = L.marker([cluster.lat, cluster.lng], { icon: marker }).addTo(layerGroup);
        m.on('click', () => {
            setActiveCluster(cluster);
        });
      });
    } else {
      pharmacies.forEach(p => {
        if (p.lat == null || p.lng == null) return;
        const colorClass = p.trust_score >= 70 ? 'safe' : p.trust_score >= 40 ? 'warn' : 'danger';
        const marker = L.divIcon({
          className: 'custom-pharmacy-marker',
          html: `<div class="pharmacy-marker pharmacy-marker--${colorClass}"></div>`,
          iconSize: [24, 24]
        });
        L.marker([p.lat, p.lng], { icon: marker }).addTo(layerGroup).bindPopup(`
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
    }
  }, [reports, pharmacies, activeTab, timeFilterDays]);

  return (
    <div className="page" style={{ paddingBottom: 0 }}>
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
              <button key={t.id} onClick={() => { setActiveTab(t.id); setActiveCluster(null); }}
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
            <div className="map-container anim" style={{ height: '100%', borderRadius: '24px', overflow: 'hidden', border: '1px solid var(--border-1)', position: 'relative' }}>
               <div ref={mapRef} style={{ height: '100%', width: '100%', background: '#0a0a0c' }} />
               {loading && (
                 <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, flexDirection: 'column', gap: '1rem' }}>
                   <div className="spinner" />
                   <div style={{ fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--accent)' }}>Decoding Terrain Data...</div>
                 </div>
               )}
               
               {/* Timeline Slider Overlay */}
               {activeTab === 'heatmap' && (
                 <div style={{ position: 'absolute', bottom: 20, left: 20, right: 20, background: 'var(--bg-secondary)', padding: '1rem', borderRadius: '12px', zIndex: 800, border: '1px solid var(--border-2)', display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-2)', whiteSpace: 'nowrap' }}>Past {timeFilterDays} Days</span>
                    <input type="range" min="1" max="365" value={timeFilterDays} onChange={e => setTimeFilterDays(Number(e.target.value))} style={{ flex: 1, accentColor: 'var(--danger)' }} />
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-3)' }}>1 Year</span>
                 </div>
               )}
               
               {!loading && activeTab === 'heatmap' && reports.length === 0 && (
                 <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(2px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 900, flexDirection: 'column', gap: '1rem', textAlign: 'center' }}>
                   <div style={{ padding: '2rem', background: 'var(--bg-secondary)', borderRadius: '16px', border: '1px solid var(--border-2)', maxWidth: '400px' }}>
                     <h3 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-1)', marginBottom: '0.5rem' }}>No Threat Clusters Detected</h3>
                     <p style={{ fontSize: '0.875rem', color: 'var(--text-3)', lineHeight: 1.5 }}>The reporting database currently has zero suspicious drug submissions in this timeframe.</p>
                   </div>
                 </div>
               )}
            </div>

            <div className="anim anim-d1" style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
               <div className="card" style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '1.5rem' }}>
                  {activeCluster ? (
                     <>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                          <h3 style={{ fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--danger)' }}>Cluster Investigation</h3>
                          <button onClick={() => setActiveCluster(null)} style={{ background: 'transparent', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: '1rem' }}>&times;</button>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                           <div>
                              <div style={{ fontSize: '2rem', fontWeight: 900, fontFamily: 'var(--mono)', color: 'var(--text-1)' }}>{activeCluster.reports.length}</div>
                              <div style={{ fontSize: '0.6875rem', fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Total Submissions</div>
                           </div>
                           <div>
                              <div style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-1)', marginBottom: '0.5rem' }}>Identified Compounds</div>
                              <ul style={{ margin: 0, paddingLeft: '1rem', color: 'var(--text-3)', fontSize: '0.75rem', lineHeight: 1.6 }}>
                                 {Array.from(new Set(activeCluster.reports.map(r => r.drug_name || 'Unknown'))).map((drug, idx) => (
                                    <li key={idx}>{drug}</li>
                                 ))}
                              </ul>
                           </div>
                           <div>
                              <div style={{ fontSize: '0.6875rem', fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Most Recent Activity</div>
                              <div style={{ fontSize: '0.875rem', color: 'var(--text-1)', marginTop: '0.2rem' }}>{Math.round(activeCluster.minDays)} days ago</div>
                           </div>
                        </div>
                     </>
                  ) : (
                     <>
                        <h3 style={{ fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-3)', marginBottom: '1.25rem' }}>Global Analytics</h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                          {[
                            { label: 'Active Alerts', val: reports.length, color: 'var(--danger)', trend: 'Monitoring' },
                            { label: 'Network Entities', val: pharmacies.length, color: 'var(--accent)', trend: 'Active' }
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
                     </>
                  )}
                  
                  <div style={{ marginTop: 'auto', borderTop: '1px solid var(--border-1)', paddingTop: '1.25rem' }}>
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-3)', lineHeight: 1.5 }}>
                      Satellite data filtered through PharmaTrace Trust Layer. Verified entities are updated every 6 hours.
                    </p>
                  </div>
               </div>
            </div>
         </div>

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

