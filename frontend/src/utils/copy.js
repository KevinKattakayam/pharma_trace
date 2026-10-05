/**
 * Central product copy.
 *
 * House style for this product:
 *  - Say what the person gets, not what the technology is. "Check a pack", not "Geospatial Intel".
 *  - Never imply certainty we do not have. A record match is not proof; a rating is not safety.
 *  - Short sentences, everyday words, no marketing adjectives. Many readers use this in a second
 *    language, on a phone, while standing at a pharmacy counter.
 *  - Tell people what to do next when something looks wrong.
 */

export const PRODUCT = {
  name: 'PharmaTrace',
  tagline: 'Check your medicine before you take it',
  intro:
    'Scan a pack to see what official records say about it, spot labels that do not add up, ' +
    'and check whether the price is within the government limit.',
};

/** The single most important sentence in the product. Shown wherever a result is displayed. */
export const SCOPE_NOTICE =
  'These checks show what official records say and whether the pack is consistent. ' +
  'They cannot prove a medicine is genuine. If something looks wrong, do not take it and ask a pharmacist.';

export const PAGE = {
  home: { title: PRODUCT.tagline, sub: PRODUCT.intro },
  scan: { title: 'Scan a medicine', sub: 'Point your camera at the barcode or QR code on the pack, or type the name.' },
  packCheck: {
    title: 'Check a pack’s label',
    sub: 'Fake packs often carry a copied QR code. Compare what the code says with what is printed on the strip or box.',
  },
  map: {
    title: 'Pharmacies and reports',
    sub: 'Pharmacies near you and places where people have reported suspicious medicines. Listings are unverified unless a regulator has approved the pharmacy’s licence claim.',
  },
  batch: { title: 'Check many packs', sub: 'For health workers and pharmacies checking a delivery. Scan each pack; you get one summary at the end.' },
  interactions: { title: 'Check medicines taken together', sub: 'See known interactions between medicines. This is general information, not advice for your situation.' },
  cabinet: { title: 'Your medicine cabinet', sub: 'Keep track of what is at home, who it is for, and when it expires.' },
  report: { title: 'Report a suspicious medicine', sub: 'Tell us what you saw. You can report without giving your name.' },
  clinic: { title: 'Clinic dashboard', sub: 'Scanning activity for your clinic.' },
  prescription: { title: 'Understand a prescription', sub: 'Photograph a prescription to see each medicine explained in plain words.' },
  sideEffects: { title: 'Side effects', sub: 'What the official label lists for this medicine.' },
  generics: { title: 'Find a cheaper equivalent', sub: 'Medicines with the same active ingredients, which often cost less.' },
  adverseEvent: { title: 'Report a side effect', sub: 'Report an unwanted effect to India’s pharmacovigilance programme (PvPI).' },
};

/** Trust claims shown on the home page. Each must be something the code actually does. */
export const WHAT_WE_DO = [
  { t: 'We never say "genuine"', s: 'Only a manufacturer’s serial check can confirm a pack. Everything else is labelled a record match.' },
  { t: 'We show our sources', s: 'Every regulator finding links to the official notice it came from.' },
  { t: 'We keep your data minimal', s: 'Your IP address is never stored. Reports can be sent without a name.' },
  { t: 'We record checks safely', s: 'Each check is added to a tamper-evident log, so a result cannot be quietly changed later.' },
];

export const PRICE_STATUS = {
  above_ceiling: { label: 'Price looks above the legal maximum', tone: 'warn' },
  within_ceiling: { label: 'Price is within the legal maximum', tone: 'safe' },
  not_scheduled: { label: 'No price limit set for this medicine', tone: 'neutral' },
  needs_confirmation: { label: 'Check the exact name and strength', tone: 'neutral' },
  need_pack_size: { label: 'Enter how many tablets are in the pack', tone: 'neutral' },
  need_mrp: { label: 'Enter the printed MRP', tone: 'neutral' },
  unavailable: { label: 'Price data not loaded', tone: 'neutral' },
  unknown: { label: 'Price not checked', tone: 'neutral' },
};

export function priceStatus(result) {
  return PRICE_STATUS[result?.status] || PRICE_STATUS.unknown;
}

/** Turn a backend error into something a person can act on. */
export function friendlyError(error) {
  const text = String(error?.message || error || '');
  if (/fetch|network|Failed to fetch/i.test(text)) return 'Could not reach the server. Check your internet connection and try again.';
  if (/401|Authentication required/i.test(text)) return 'Please sign in to continue.';
  if (/403|Insufficient role|Not authorised/i.test(text)) return 'Your account does not have access to this.';
  if (/404|not found/i.test(text)) return 'We could not find that.';
  if (/409|CONFLICT/i.test(text)) return 'This was changed somewhere else. Reload and try again.';
  if (/413/i.test(text)) return 'That is too large. Try fewer items or a smaller photo.';
  if (/429|rate limit/i.test(text)) return 'Too many requests. Wait a minute and try again.';
  if (/503|unavailable/i.test(text)) return 'The service is busy. Please try again shortly.';
  return text || 'Something went wrong. Please try again.';
}
