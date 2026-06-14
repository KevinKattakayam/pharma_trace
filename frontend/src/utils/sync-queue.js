const DB_VERSION = 2;

export const addToSyncQueue = (endpoint, payload) => {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('PharmaTraceCache', DB_VERSION);
    request.onsuccess = (event) => {
       const db = event.target.result;
       if (!db.objectStoreNames.contains('sync_queue')) return resolve();
       const tx = db.transaction(['sync_queue'], 'readwrite');
       const store = tx.objectStore('sync_queue');
       store.put({
          endpoint,
          payload,
          retry_count: 0,
          created_at: Date.now()
       });
       tx.oncomplete = () => resolve();
       tx.onerror = () => reject(tx.error);
    };
    request.onerror = () => reject();
  });
};

export const getSyncQueue = () => {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('PharmaTraceCache', DB_VERSION);
    request.onsuccess = (event) => {
       const db = event.target.result;
       if (!db.objectStoreNames.contains('sync_queue')) return resolve([]);
       const tx = db.transaction(['sync_queue'], 'readonly');
       const store = tx.objectStore('sync_queue');
       const getReq = store.getAll();
       getReq.onsuccess = () => resolve(getReq.result || []);
       getReq.onerror = () => reject();
    };
    request.onerror = () => reject();
  });
}

export const removeFromSyncQueue = (id) => {
  return new Promise((resolve) => {
    const request = indexedDB.open('PharmaTraceCache', DB_VERSION);
    request.onsuccess = (event) => {
       const db = event.target.result;
       if (!db.objectStoreNames.contains('sync_queue')) return resolve();
       const tx = db.transaction(['sync_queue'], 'readwrite');
       const store = tx.objectStore('sync_queue');
       store.delete(id);
       tx.oncomplete = () => resolve();
    };
  });
};

export const updateSyncQueueRetry = (id, newCount) => {
  return new Promise((resolve) => {
    const request = indexedDB.open('PharmaTraceCache', DB_VERSION);
    request.onsuccess = (event) => {
       const db = event.target.result;
       if (!db.objectStoreNames.contains('sync_queue')) return resolve();
       const tx = db.transaction(['sync_queue'], 'readwrite');
       const store = tx.objectStore('sync_queue');
       const getReq = store.get(id);
       getReq.onsuccess = () => {
          if (getReq.result) {
             store.put({ ...getReq.result, retry_count: newCount });
          }
       };
       tx.oncomplete = () => resolve();
    };
  });
};
