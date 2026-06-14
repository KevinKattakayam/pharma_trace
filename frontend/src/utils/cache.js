export const SCHEMA_VERSION = '1.1';
const DB_VERSION = 2;

export const requestPersistentStorage = async () => {
  if (navigator.storage && navigator.storage.persist) {
    const isPersisted = await navigator.storage.persist();
    return isPersisted;
  }
  return false;
};

export const initOfflineCache = async () => {
  try {
    if (navigator.storage && navigator.storage.estimate) {
      const estimate = await navigator.storage.estimate();
      const quota = estimate.quota || 0;
      const usage = estimate.usage || 0;
      if (quota > 0) {
        const availablePct = ((quota - usage) / quota) * 100;
        if (availablePct < 20) {
          console.warn(`Storage space low: ${availablePct.toFixed(1)}% remaining`);
          // Note: In a real app, you'd dispatch a React event here to show a UI warning.
          window.dispatchEvent(new CustomEvent('storage-warning', { detail: { availablePct } }));
        }
      }
    }

    const request = indexedDB.open('PharmaTraceCache', DB_VERSION);
    
    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains('medicines')) {
        db.createObjectStore('medicines', { keyPath: 'name' });
      }
      if (!db.objectStoreNames.contains('meta')) {
        db.createObjectStore('meta', { keyPath: 'key' });
      }
      if (!db.objectStoreNames.contains('scan_history')) {
        db.createObjectStore('scan_history', { keyPath: 'id', autoIncrement: true });
      }
      if (!db.objectStoreNames.contains('sync_queue')) {
        db.createObjectStore('sync_queue', { keyPath: 'id', autoIncrement: true });
      }
    };
    
    request.onsuccess = async (event) => {
      const db = event.target.result;
      
      // Check schema version
      const metaTx = db.transaction(['meta'], 'readonly');
      const metaStore = metaTx.objectStore('meta');
      const versionReq = metaStore.get('schema_version');
      
      versionReq.onsuccess = async () => {
        const storedVersion = versionReq.result?.value;
        if (storedVersion !== SCHEMA_VERSION) {
          console.log('Schema version mismatch. Wiping and reseeding cache...');
          const clearTx = db.transaction(['medicines', 'meta'], 'readwrite');
          clearTx.objectStore('medicines').clear();
          clearTx.objectStore('meta').put({ key: 'schema_version', value: SCHEMA_VERSION });
          await fetchAndSeed(db);
        } else {
          // Check if we need a periodic refresh
          const lastSeedReq = metaStore.get('last_seeded_at');
          lastSeedReq.onsuccess = async () => {
             const lastSeeded = lastSeedReq.result?.value || 0;
             const ageDays = (Date.now() - lastSeeded) / (1000 * 60 * 60 * 24);
             if (ageDays > 7) {
                 // Trigger silent background refresh
                 console.log('Cache older than 7 days, refreshing...');
                 fetchAndSeed(db).catch(console.error);
             }
          }
        }
      };
    };
  } catch (error) {
    console.log('Offline cache init failed:', error);
  }
};

async function fetchAndSeed(db) {
  const response = await fetch('/api/v1/drugs/common-indian-medicines');
  if (!response.ok) return;
  const data = await response.json();
  
  const transaction = db.transaction(['medicines', 'meta'], 'readwrite');
  const store = transaction.objectStore('medicines');
  const metaStore = transaction.objectStore('meta');
  
  const now = Date.now();
  data.medicines.forEach(med => {
    store.put({
      ...med,
      cached_at: now
    });
  });
  
  metaStore.put({ key: 'last_seeded_at', value: now });
}

// Levenshtein distance for fuzzy searching
const levenshtein = (a, b) => {
  if (a.length === 0) return b.length;
  if (b.length === 0) return a.length;

  const matrix = [];
  for (let i = 0; i <= b.length; i++) {
    matrix[i] = [i];
  }
  for (let j = 0; j <= a.length; j++) {
    matrix[0][j] = j;
  }

  for (let i = 1; i <= b.length; i++) {
    for (let j = 1; j <= a.length; j++) {
      if (b.charAt(i - 1) === a.charAt(j - 1)) {
        matrix[i][j] = matrix[i - 1][j - 1];
      } else {
        matrix[i][j] = Math.min(
          matrix[i - 1][j - 1] + 1, // substitution
          Math.min(
            matrix[i][j - 1] + 1, // insertion
            matrix[i - 1][j] + 1 // deletion
          )
        );
      }
    }
  }
  return matrix[b.length][a.length];
};

export const checkOfflineCache = (query) => {
  return new Promise((resolve) => {
    if (!query) return resolve(null);
    const request = indexedDB.open('PharmaTraceCache', DB_VERSION);
    
    request.onsuccess = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains('medicines')) {
        return resolve(null);
      }
      
      const transaction = db.transaction(['medicines'], 'readonly');
      const store = transaction.objectStore('medicines');
      const getAllRequest = store.getAll();
      
      getAllRequest.onsuccess = () => {
        const meds = getAllRequest.result;
        const qStr = query.toLowerCase().trim();
        const dosageRegex = /(\d+(?:\.\d+)?\s*(?:mg|ml|mcg|g|iu|%))/i;
        const qDosageMatch = qStr.match(dosageRegex);
        const qDosage = qDosageMatch ? qDosageMatch[1].replace(/\s/g, '') : null;
        
        let bestMatch = null;
        let maxSimilarity = 0;
        let isExact = false;
        let identificationUncertain = false;

        // Reject records older than 7 days
        const now = Date.now();
        const validMeds = meds.filter(m => {
           if (!m.cached_at) return false;
           const ageDays = (now - m.cached_at) / (1000 * 60 * 60 * 24);
           return ageDays <= 7;
        });

        validMeds.forEach(m => {
          const names = [
            m.name?.toLowerCase(), 
            m.generic_name?.toLowerCase(), 
            m.ndc?.toLowerCase(), 
            m.cdsco_code?.toLowerCase()
          ].filter(Boolean);
          
          for (const name of names) {
            if (name === qStr) {
              bestMatch = m;
              isExact = true;
              maxSimilarity = 1;
              identificationUncertain = false;
              break;
            }
            // Fuzzy search calculation
            const maxLength = Math.max(name.length, qStr.length);
            const dist = levenshtein(name, qStr);
            const similarity = (maxLength - dist) / maxLength;
            
            if (similarity > maxSimilarity && similarity > 0.85) {
              maxSimilarity = similarity;
              bestMatch = m;
              isExact = false;
            }
          }
        });
        
        if (bestMatch && !isExact) {
            // Confirm exact match on strength/dosage field
            const mDosageMatch = (bestMatch.name || '').toLowerCase().match(dosageRegex) || (bestMatch.dosage || '').toLowerCase().match(dosageRegex);
            const mDosage = mDosageMatch ? mDosageMatch[1].replace(/\s/g, '') : null;
            if (qDosage && mDosage && qDosage !== mDosage) {
               identificationUncertain = true;
            } else if (qDosage && !mDosage) {
               identificationUncertain = true;
            } else if (!qDosage && mDosage) {
               identificationUncertain = true; // Missing dosage in scan but drug has one
            }
        }
        
        if (bestMatch) {
           resolve({
              ...bestMatch,
              fuzzy_matched: !isExact,
              similarity: maxSimilarity,
              identification_uncertain: identificationUncertain
           });
        } else {
           resolve(null);
        }
      };
      
      getAllRequest.onerror = () => resolve(null);
    };
    request.onerror = () => resolve(null);
  });
};

export const saveOfflineScan = async (scanData) => {
  // Rather than writing directly to scan_history, we POST it to the backend.
  // If the device is offline, the Service Worker intercepts this and queues it in the outbox.
  try {
     await fetch('/api/v1/verify/offline-sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
           ...scanData,
           source: scanData.identification_uncertain ? 'uncertain' : (scanData.fuzzy_matched ? 'fuzzy_offline' : 'offline_cache'),
           verified_at: new Date().toISOString()
        })
     });
  } catch (err) {
     console.log('Offline scan intercepted by Background Sync queue.', err);
  }
};
