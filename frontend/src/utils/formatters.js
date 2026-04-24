export function formatConfidence(value) {
  return `${Math.round(value)}%`;
}

export function getConfidenceColor(value) {
  if (value >= 80) return 'var(--safe)';
  if (value >= 50) return 'var(--warn)';
  return 'var(--danger)';
}

export function getVerdictLabel(verdict) {
  const labels = {
    authentic: 'Verified Authentic',
    suspicious: 'Suspicious — Verify Manually',
    counterfeit: 'Likely Counterfeit',
    unknown: 'Unable to Verify'
  };
  return labels[verdict] || verdict;
}

export function getVerdictClass(verdict) {
  const classes = {
    authentic: 'safe',
    suspicious: 'warn',
    counterfeit: 'danger',
    unknown: 'info'
  };
  return classes[verdict] || 'info';
}

export function getSeverityLabel(severity) {
  const labels = {
    none: 'No Interaction',
    minor: 'Minor',
    moderate: 'Moderate',
    major: 'Major',
    contraindicated: 'Contraindicated'
  };
  return labels[severity] || severity;
}

export function getSeverityColor(severity) {
  const colors = {
    none: 'var(--text-3)',
    minor: 'var(--info)',
    moderate: 'var(--warn)',
    major: 'var(--danger)',
    contraindicated: 'var(--danger)'
  };
  return colors[severity] || 'var(--text-3)';
}

export function formatNDC(ndc) {
  if (!ndc) return '—';
  const clean = ndc.replace(/\D/g, '');
  if (clean.length === 10) {
    return `${clean.slice(0, 4)}-${clean.slice(4, 8)}-${clean.slice(8)}`;
  }
  return ndc;
}

export function formatDate(dateStr) {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  });
}

export function timeAgo(dateStr) {
  const now = new Date();
  const d = new Date(dateStr);
  const seconds = Math.floor((now - d) / 1000);

  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
  return formatDate(dateStr);
}

export function truncate(str, maxLen = 100) {
  if (!str || str.length <= maxLen) return str;
  return str.slice(0, maxLen) + '…';
}

export function debounce(fn, ms = 300) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}
