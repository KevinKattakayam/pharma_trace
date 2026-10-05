/** Honest display helpers for pharmacy listings. Pure functions (unit-tested). */

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

/** Escape text before putting it in an HTML string (Leaflet popups). Pharmacy names/addresses are user- or OSM-supplied. */
export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
}

export const LISTING_LABEL = {
  osm_unverified: 'Unverified: location from OpenStreetMap',
  community_unverified: 'Unverified: added by a community member',
  claim_verified: 'Licence claim approved by a regulator',
};

export function listingLabel(pharmacy) {
  return LISTING_LABEL[pharmacy?.listing_status] || LISTING_LABEL.community_unverified;
}

/** A community star rating, never a safety verdict. */
export function ratingText(pharmacy) {
  const n = pharmacy?.review_count ?? 0;
  if (pharmacy?.trust_score == null) {
    return pharmacy?.rating_status === 'not_enough_reviews' ? `Not enough reviews yet (${n})` : 'Not rated yet';
  }
  return `Community rating ${pharmacy.average_rating}★ from ${n} reviews`;
}

export function ratingTone(pharmacy) {
  const s = pharmacy?.trust_score;
  if (s == null) return 'warn';
  return s >= 70 ? 'safe' : s >= 40 ? 'warn' : 'danger';
}

export const hasOsmListings = (list) => (list || []).some((p) => String(p.source || '').includes('OpenStreetMap'));
export const OSM_ATTRIBUTION = 'Pharmacy locations © OpenStreetMap contributors (ODbL)';
