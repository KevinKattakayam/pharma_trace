import { describe, expect, it } from 'vitest';
import { escapeHtml, hasOsmListings, listingLabel, ratingText, ratingTone } from './pharmacyView';

describe('escapeHtml', () => {
  it('neutralises script injection from names and addresses', () => {
    const out = escapeHtml('<img src=x onerror="alert(1)">Meds & "Co"');
    expect(out).not.toMatch(/[<>"]/);
    expect(out).toContain('&lt;img');
  });
  it('handles null and numbers', () => {
    expect(escapeHtml(null)).toBe('');
    expect(escapeHtml(5)).toBe('5');
  });
});

describe('ratingText', () => {
  it('never invents a score for unrated listings', () => {
    expect(ratingText({ trust_score: null, rating_status: 'not_rated' })).toBe('Not rated yet');
    expect(ratingText({ trust_score: null, rating_status: 'not_enough_reviews', review_count: 1 })).toMatch(/Not enough reviews/);
    expect(ratingText({})).toBe('Not rated yet');
  });
  it('shows stars and count when rated, labelled as community rating', () => {
    expect(ratingText({ trust_score: 80, average_rating: 4.5, review_count: 12 })).toBe('Community rating 4.5★ from 12 reviews');
  });
  it('unrated listings get a neutral caution tone, not green', () => {
    expect(ratingTone({ trust_score: null })).toBe('warn');
    expect(ratingTone({ trust_score: 90 })).toBe('safe');
    expect(ratingTone({ trust_score: 10 })).toBe('danger');
  });
});

describe('listingLabel', () => {
  it('only a regulator-approved claim reads as verified', () => {
    expect(listingLabel({ listing_status: 'claim_verified' })).toMatch(/regulator/);
    expect(listingLabel({ listing_status: 'osm_unverified' })).toMatch(/^Unverified/);
    expect(listingLabel({})).toMatch(/^Unverified/);
  });
});

describe('attribution', () => {
  it('detects OpenStreetMap-sourced listings', () => {
    expect(hasOsmListings([{ source: 'OpenStreetMap contributors (ODbL)' }])).toBe(true);
    expect(hasOsmListings([{ source: null }, {}])).toBe(false);
  });
});
