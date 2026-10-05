/** In-memory session token backed by encrypted IndexedDB (see cryptoStorage.js). */
import { clearStoredToken, getDecryptedTokenFromIndexedDB, storeEncryptedTokenInIndexedDB } from './cryptoStorage';

const LEGACY_KEY = 'pharmatrace_token';
let cached;

/** Returns the bearer token or null. Migrates and deletes any legacy plaintext copy. */
export async function getToken() {
  if (cached !== undefined) return cached;
  const legacy = typeof localStorage !== 'undefined' ? localStorage.getItem(LEGACY_KEY) : null;
  if (legacy) {
    localStorage.removeItem(LEGACY_KEY);
    await storeEncryptedTokenInIndexedDB(legacy);
    cached = legacy;
    return cached;
  }
  cached = await getDecryptedTokenFromIndexedDB();
  return cached;
}

export async function setToken(token) {
  cached = token || null;
  if (typeof localStorage !== 'undefined') localStorage.removeItem(LEGACY_KEY);
  await (token ? storeEncryptedTokenInIndexedDB(token) : clearStoredToken());
}

export async function clearToken() {
  return setToken(null);
}
