/** Plain-language copy for verification results. Pure functions (unit-tested). */
export const REASON_TEXT = {
  serial_rejected: 'The manufacturer’s verification service rejected this pack’s serial number.',
  active_recall: 'A regulator or manufacturer recall matches this product.',
  batch_alert: 'This batch number is listed in a regulator quality alert.',
  invalid_check_digit: 'The barcode’s check digit is wrong, a sign of misprinting or tampering.',
  registry_miss: 'This product code was not found in the official registry for its code type.',
  expired: 'The pack is past its expiry date.',
  label_inconsistent: 'Information in the code does not match what is printed on the pack.',
  vision_high_suspicion: 'Photo analysis noticed possible packaging problems (AI, unverified).',
};

export const VERDICT_COPY = {
  authentic: { label: 'Confirmed by manufacturer', tone: 'ok', advice: 'The manufacturer’s serial check confirmed this pack.' },
  counterfeit: { label: 'Rejected by manufacturer', tone: 'danger', advice: 'Do not use. Keep the pack and report it to a pharmacist or CDSCO.' },
  suspicious: { label: 'Problems found', tone: 'warn', advice: 'Do not use until a pharmacist has checked it.' },
  unknown: { label: 'Not verified', tone: 'neutral', advice: 'A record was found, but that does not prove this pack is genuine. Check with a pharmacist if unsure.' },
};

export function describeVerdict(verdict, reasons = []) {
  const base = VERDICT_COPY[verdict] || VERDICT_COPY.unknown;
  return { ...base, reasons: reasons.map((r) => REASON_TEXT[r] || r) };
}

export function recallText(status) {
  return {
    active: 'Active recall or alert found',
    none_found: 'No recall found in the sources checked',
    inconclusive: 'Recall status unknown: a source was unavailable',
  }[status] || 'Recall status unknown';
}
