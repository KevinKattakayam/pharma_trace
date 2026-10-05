const EXPIRY_PATTERNS = [
  /exp[iry\s:.]*(\d{2}[/-]\d{2,4})/i,
  /use\s+before[:\s]+(\w+\s+\d{4})/i,
  /best\s+before[:\s]+(\w+\s+\d{4})/i,
  /expiry[:\s]+(\d{2}[/-]\d{2,4})/i,
  /expires?[:\s]+(\d{2}[/-]\d{2,4})/i,
  /e[:\s]+(\d{2}[/-]\d{2,4})/i,
  /समाप्ति[:\s]*(\d{2}[/-]\d{2,4})/i,
  /കാലഹരണ[:\s]*(\d{2}[/-]\d{2,4})/i
];

export function extractExpiryDate(text) {
  if (!text) {
    return { expiry_date: null, days_remaining: null, status: 'unknown' };
  }

  for (const pattern of EXPIRY_PATTERNS) {
    const match = text.match(pattern);
    if (match) {
      try {
        const dateStr = match[1];
        // simple parsing
        const parts = dateStr.split(/[/-]/);
        let parsedDate;
        
        if (parts.length === 2) {
            // MM/YY or MM/YYYY
            let month = parseInt(parts[0], 10) - 1;
            let year = parseInt(parts[1], 10);
            if (year < 100) year += 2000;
            
            // set to end of month
            parsedDate = new Date(year, month + 1, 0);
        } else {
            parsedDate = new Date(dateStr);
        }

        if (!isNaN(parsedDate.getTime())) {
          const today = new Date();
          const daysRemaining = Math.floor((parsedDate - today) / (1000 * 60 * 60 * 24));
          
          let status;
          if (daysRemaining < 0) status = 'expired';
          else if (daysRemaining < 90) status = 'expiring_soon';
          else status = 'safe';

          const monthName = parsedDate.toLocaleString('en-US', { month: 'long' });
          const year = parsedDate.getFullYear();

          return {
            expiry_date: `${monthName} ${year}`,
            days_remaining: daysRemaining,
            status,
            raw_date: parsedDate.toISOString()
          };
        }
      } catch (err) {
        // ignore
      }
    }
  }

  return { expiry_date: null, days_remaining: null, status: 'unknown' };
}
