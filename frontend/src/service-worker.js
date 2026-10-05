import { clientsClaim } from 'workbox-core';
import { precacheAndRoute } from 'workbox-precaching';
import { registerRoute } from 'workbox-routing';
import { StaleWhileRevalidate, NetworkFirst, CacheFirst } from 'workbox-strategies';
import { ExpirationPlugin } from 'workbox-expiration';
import { getDecryptedTokenFromIndexedDB } from './utils/cryptoStorage';

self.skipWaiting();
clientsClaim();

// Precache static assets built by Vite
precacheAndRoute(self.__WB_MANIFEST || []);

// StaleWhileRevalidate for common GET endpoints
registerRoute(
  ({ url }) => url.pathname.match(/^\/api\/v1\/drugs\//) || url.pathname.match(/^\/api\/v1\/pharmacies\/nearby/),
  new StaleWhileRevalidate({
    cacheName: 'api-get-cache',
    plugins: [
      new ExpirationPlugin({
        maxEntries: 100,
        maxAgeSeconds: 24 * 60 * 60, // 24 hours
      }),
    ],
  })
);

// NetworkFirst with 4-second timeout for verification endpoints
registerRoute(
  ({ url }) => url.pathname.match(/^\/api\/v1\/verify\//),
  new NetworkFirst({
    cacheName: 'api-verify-cache',
    networkTimeoutSeconds: 4,
    plugins: [
      new ExpirationPlugin({
        maxEntries: 50,
        maxAgeSeconds: 24 * 60 * 60,
      }),
    ],
  })
);

// OpenFDA API caching
registerRoute(
  ({ url }) => url.href.match(/^https:\/\/api\.fda\.gov\/.*/i),
  new CacheFirst({
    cacheName: 'openfda-cache',
    plugins: [
      new ExpirationPlugin({
        maxEntries: 200,
        maxAgeSeconds: 24 * 60 * 60,
      }),
    ],
  })
);

// Custom Background Sync Implementation for POST requests
const DB_VERSION = 2;

self.addEventListener('fetch', (event) => {
  if (event.request.method === 'POST') {
    const reqClone = event.request.clone();
    
    event.respondWith(
      fetch(event.request).catch(async (err) => {
         // Intercept failed POSTs
         const bodyText = await reqClone.text();
         await saveToCustomSyncQueue(event.request.url, bodyText);
         
         // Try to register sync
         if ('sync' in self.registration) {
            self.registration.sync.register('process-outbox').catch(console.error);
         }
         
         // Return a mock successful response to the app so it doesn't crash
         return new Response(JSON.stringify({ offline_queued: true, message: "Saved to outbox for sync" }), {
           headers: { 'Content-Type': 'application/json' }
         });
      })
    );
  }
});

self.addEventListener('sync', (event) => {
  if (event.tag === 'process-outbox') {
    event.waitUntil(processCustomSyncQueue());
  }
});

function saveToCustomSyncQueue(url, bodyText) {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('PharmaTraceCache', DB_VERSION);
    request.onsuccess = (e) => {
       const db = e.target.result;
       if (!db.objectStoreNames.contains('sync_queue')) return resolve();
       const tx = db.transaction(['sync_queue'], 'readwrite');
       const store = tx.objectStore('sync_queue');
       store.put({
          endpoint: url,
          payload: bodyText,
          retry_count: 0,
          created_at: Date.now()
       });
       tx.oncomplete = () => {
          const bc = new BroadcastChannel('sync-updates');
          bc.postMessage({ type: 'OUTBOX_UPDATE', payload: { status: 'ITEM_ADDED' } });
          resolve();
       };
    };
    request.onerror = () => reject();
  });
}

async function processCustomSyncQueue() {
  const db = await new Promise((resolve, reject) => {
     const req = indexedDB.open('PharmaTraceCache', DB_VERSION);
     req.onsuccess = e => resolve(e.target.result);
     req.onerror = () => reject();
  });
  
  if (!db.objectStoreNames.contains('sync_queue')) return;

  const items = await new Promise(resolve => {
     const tx = db.transaction(['sync_queue'], 'readonly');
     const getReq = tx.objectStore('sync_queue').getAll();
     getReq.onsuccess = () => resolve(getReq.result || []);
  });
  
  // Sort FIFO
  items.sort((a, b) => a.created_at - b.created_at);
  
  const bc = new BroadcastChannel('sync-updates');

  for (const item of items) {
     // Skip items older than 7 days
     if (Date.now() - item.created_at > 7 * 24 * 60 * 60 * 1000) continue;
     
     // Skip if max retries exceeded
     if (item.retry_count >= 5) continue;
     
     try {
        const headers = { 'Content-Type': 'application/json' };
        
        // Fetch fresh AES-GCM decrypted auth token right before replay
        const tokenReq = await getDecryptedTokenFromIndexedDB();
        if (tokenReq) {
           headers['Authorization'] = `Bearer ${tokenReq}`;
        }

        // OCC: Send entity version as If-Match header for conflict detection
        if (item.entity_version) {
           headers['If-Match'] = item.entity_version;
        }
        
        const response = await fetch(item.endpoint, {
          method: 'POST',
          headers: headers,
          body: item.payload
        });
        
        if (response.ok) {
           await new Promise(r => {
             const tx = db.transaction(['sync_queue'], 'readwrite');
             tx.objectStore('sync_queue').delete(item.id);
             tx.oncomplete = r;
           });
           bc.postMessage({ type: 'OUTBOX_UPDATE', payload: { status: 'SYNC_SUCCESS', id: item.id } });
        } else if (response.status === 409) {
           // OCC CONFLICT: Server state has diverged from the offline snapshot.
           // Mark item as conflicted and notify UI for manual 3-way reconciliation.
           let serverDelta = null;
           try { serverDelta = await response.json(); } catch { serverDelta = null; /* non-JSON conflict body */ }
           await new Promise(r => {
             const tx = db.transaction(['sync_queue'], 'readwrite');
             tx.objectStore('sync_queue').put({
               ...item,
               conflict_status: '409_conflict',
               server_delta: serverDelta,
               conflict_detected_at: Date.now()
             });
             tx.oncomplete = r;
           });
           bc.postMessage({
             type: 'OUTBOX_UPDATE',
             payload: {
               status: 'SYNC_CONFLICT',
               id: item.id,
               server_delta: serverDelta,
               message: 'Server data changed while offline. Manual review required.'
             }
           });
        } else {
           await new Promise(r => {
             const tx = db.transaction(['sync_queue'], 'readwrite');
             tx.objectStore('sync_queue').put({ ...item, retry_count: item.retry_count + 1 });
             tx.oncomplete = r;
           });
           bc.postMessage({ type: 'OUTBOX_UPDATE', payload: { status: 'SYNC_FAILED', id: item.id } });
        }
     } catch (err) {
        await new Promise(r => {
          const tx = db.transaction(['sync_queue'], 'readwrite');
          tx.objectStore('sync_queue').put({ ...item, retry_count: item.retry_count + 1 });
          tx.oncomplete = r;
        });
        bc.postMessage({ type: 'OUTBOX_UPDATE', payload: { status: 'SYNC_FAILED', id: item.id } });
     }
  }
}

// ═══════════════════════════════════════════════
// Web Push Notifications
// ═══════════════════════════════════════════════

self.addEventListener('push', function(event) {
  if (event.data) {
    try {
      const data = event.data.json();
      const title = data.title || 'PharmaTrace Update';
      const options = {
        body: data.body || 'You have a new alert regarding your medication.',
        icon: '/icons/icon-192x192.png',
        badge: '/icons/icon-192x192.png',
        vibrate: [100, 50, 100],
        data: {
          url: data.url || '/'
        }
      };

      event.waitUntil(self.registration.showNotification(title, options));
    } catch (err) {
      console.error('Push event data was not JSON:', err);
    }
  }
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  const urlToOpen = event.notification.data?.url || '/';
  
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
      for (let i = 0; i < clientList.length; i++) {
        let client = clientList[i];
        if (client.url.includes(urlToOpen) && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(urlToOpen);
      }
    })
  );
});
