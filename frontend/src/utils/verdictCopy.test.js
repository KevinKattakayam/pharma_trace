import { describe, expect, it } from 'vitest';
import { describeVerdict, recallText, REASON_TEXT } from './verdictCopy';

describe('describeVerdict', () => {
  it('never tells users an unverified pack is genuine', () => {
    const v = describeVerdict('unknown');
    expect(v.label).toBe('Not verified');
    expect(v.advice).toMatch(/does not prove/);
  });
  it('maps every backend reason code to plain language', () => {
    const codes = Object.keys(REASON_TEXT);
    expect(describeVerdict('suspicious', codes).reasons.every((r) => !codes.includes(r))).toBe(true);
  });
  it('falls back safely for unknown verdicts and codes', () => {
    expect(describeVerdict('weird', ['new_code'])).toMatchObject({ label: 'Not verified', reasons: ['new_code'] });
  });
  it('counterfeit tells the user not to use it', () => {
    expect(describeVerdict('counterfeit').advice).toMatch(/Do not use/);
  });
});

describe('recallText', () => {
  it('never reports inconclusive as clear', () => {
    expect(recallText('inconclusive')).toMatch(/unknown/);
    expect(recallText(undefined)).toMatch(/unknown/);
  });
});
