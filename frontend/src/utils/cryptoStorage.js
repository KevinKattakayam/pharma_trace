/**
 * Secure Web Crypto API SubtleCrypto AES-GCM Offline Storage
 * Derives a device-bound encryption key via PBKDF2 to store JWTs safely in IndexedDB.
 * Fully compatible with both DOM window and Service Worker execution threads.
 */

const DB_NAME = 'PharmaTraceCache';
const DB_VERSION = 2;

/**
 * Get or create device entropy salt stored in IndexedDB 'meta' store.
 */
async function getDeviceEntropy() {
  return new Promise((resolve) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onsuccess = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains('meta')) return resolve('pharmatrace_default_entropy');
      const tx = db.transaction(['meta'], 'readwrite');
      const store = tx.objectStore('meta');
      const getReq = store.get('device_entropy_salt');
      
      getReq.onsuccess = () => {
        if (getReq.result?.value) {
          resolve(getReq.result.value);
        } else {
          const randomBytes = self.crypto.getRandomValues(new Uint8Array(16));
          const hex = Array.from(randomBytes).map(b => b.toString(16).padStart(2, '0')).join('');
          store.put({ key: 'device_entropy_salt', value: hex });
          resolve(hex);
        }
      };
      getReq.onerror = () => resolve('pharmatrace_default_entropy');
    };
    request.onerror = () => resolve('pharmatrace_default_entropy');
  });
}

/**
 * Derive AES-GCM 256-bit encryption key using PBKDF2 SubtleCrypto.
 */
async function deriveStorageKey() {
  const entropy = await getDeviceEntropy();
  const encoder = new TextEncoder();
  const baseKey = await self.crypto.subtle.importKey(
    "raw",
    encoder.encode(entropy + (self.navigator ? self.navigator.userAgent : "service-worker")),
    { name: "PBKDF2" },
    false,
    ["deriveKey"]
  );

  return self.crypto.subtle.deriveKey(
    {
      name: "PBKDF2",
      salt: encoder.encode(entropy),
      iterations: 100000,
      hash: "SHA-256"
    },
    baseKey,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"]
  );
}

/**
 * Encrypt a plaintext JWT and persist ciphertext to IndexedDB 'meta' store.
 */
export async function storeEncryptedTokenInIndexedDB(plaintextToken) {
  if (!plaintextToken) return;
  try {
    const key = await deriveStorageKey();
    const iv = self.crypto.getRandomValues(new Uint8Array(12));
    const encoder = new TextEncoder();
    const ciphertext = await self.crypto.subtle.encrypt(
      { name: "AES-GCM", iv },
      key,
      encoder.encode(plaintextToken)
    );

    const ivHex = Array.from(iv).map(b => b.toString(16).padStart(2, '0')).join('');
    const cipherHex = Array.from(new Uint8Array(ciphertext)).map(b => b.toString(16).padStart(2, '0')).join('');
    const encryptedPayload = `${ivHex}:${cipherHex}`;

    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onsuccess = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains('meta')) return;
      const tx = db.transaction(['meta'], 'readwrite');
      tx.objectStore('meta').put({ key: 'auth_token', value: encryptedPayload });
    };
  } catch (err) {
    console.error("AES-GCM token storage failed:", err);
  }
}

/**
 * Decrypt and retrieve the plaintext JWT from IndexedDB 'meta' store.
 */
export async function getDecryptedTokenFromIndexedDB() {
  return new Promise((resolve) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onsuccess = async (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains('meta')) return resolve(null);
      const tx = db.transaction(['meta'], 'readonly');
      const getReq = tx.objectStore('meta').get('auth_token');
      
      getReq.onsuccess = async () => {
        const encryptedPayload = getReq.result?.value;
        if (!encryptedPayload) return resolve(null);
        if (!encryptedPayload.includes(':')) return resolve(encryptedPayload); // Legacy unencrypted fallback
        
        try {
          const [ivHex, cipherHex] = encryptedPayload.split(':');
          const iv = new Uint8Array(ivHex.match(/.{1,2}/g).map(byte => parseInt(byte, 16)));
          const ciphertext = new Uint8Array(cipherHex.match(/.{1,2}/g).map(byte => parseInt(byte, 16)));
          
          const key = await deriveStorageKey();
          const decrypted = await self.crypto.subtle.decrypt(
            { name: "AES-GCM", iv },
            key,
            ciphertext
          );
          resolve(new TextDecoder().decode(decrypted));
        } catch (err) {
          console.error("AES-GCM token decryption failed:", err);
          resolve(null);
        }
      };
      getReq.onerror = () => resolve(null);
    };
    request.onerror = () => resolve(null);
  });
}
