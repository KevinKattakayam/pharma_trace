import { describe, expect, it } from 'vitest';
import { friendlyError, PAGE, priceStatus, SCOPE_NOTICE, WHAT_WE_DO } from './copy';

describe('scope notice', () => {
  it('states the limit and tells people what to do', () => {
    expect(SCOPE_NOTICE).toMatch(/cannot prove/i);
    expect(SCOPE_NOTICE).toMatch(/ask a pharmacist/i);
  });
});

describe('page copy', () => {
  it('avoids jargon and marketing words', () => {
    const banned = /zero-knowledge|geospatial|real-time|enterprise|intel\b|neural|matrix|protocol|edge mode|high-throughput|cutting-edge|seamless|revolution/i;
    for (const [key, { title, sub }] of Object.entries(PAGE)) {
      expect(`${key}: ${title}`, `${key} title`).not.toMatch(banned);
      expect(`${key}: ${sub}`, `${key} subtitle`).not.toMatch(banned);
    }
  });
  it('keeps titles short and subtitles readable', () => {
    for (const [key, { title, sub }] of Object.entries(PAGE)) {
      expect(title.length, `${key} title length`).toBeLessThan(40);
      expect(sub.length, `${key} subtitle length`).toBeLessThan(220);
    }
  });
});

describe('home claims', () => {
  it('leads with the limit rather than a boast', () => {
    expect(WHAT_WE_DO[0].t).toMatch(/never say/i);
    expect(WHAT_WE_DO.map((x) => x.t).join(' ')).not.toMatch(/zero-knowledge|military|bank-grade/i);
  });
});

describe('priceStatus', () => {
  it('labels an over-ceiling price as a warning, not a counterfeit claim', () => {
    const s = priceStatus({ status: 'above_ceiling' });
    expect(s.tone).toBe('warn');
    expect(s.label).not.toMatch(/fake|counterfeit/i);
  });
  it('falls back safely', () => {
    expect(priceStatus(undefined).label).toBe('Price not checked');
    expect(priceStatus({ status: 'something_new' }).label).toBe('Price not checked');
  });
});

describe('friendlyError', () => {
  it('explains common failures in plain words', () => {
    expect(friendlyError(new Error('Failed to fetch'))).toMatch(/internet connection/);
    expect(friendlyError(new Error('HTTP 429 rate limit'))).toMatch(/Wait a minute/);
    expect(friendlyError(new Error('401 Authentication required'))).toMatch(/sign in/);
    expect(friendlyError(null)).toMatch(/Something went wrong/);
  });
});
