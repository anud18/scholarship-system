/**
 * Unit tests for PII masking utilities
 */

import { maskIdNumber } from './mask';

describe('maskIdNumber', () => {
  it('should keep the first character and last three characters of a typical 10-char ID', () => {
    expect(maskIdNumber('A123456789')).toBe('A******789');
    expect(maskIdNumber('F229876543')).toBe('F******543');
  });

  it('should mask everything between the first and last three characters for other lengths', () => {
    expect(maskIdNumber('AB12345')).toBe('A***345');
    expect(maskIdNumber('A1234')).toBe('A*234');
  });

  it('should keep only the first character for values of four characters or fewer', () => {
    expect(maskIdNumber('ABCD')).toBe('A***');
    expect(maskIdNumber('ABC')).toBe('A**');
    expect(maskIdNumber('AB')).toBe('A*');
    expect(maskIdNumber('A')).toBe('A');
  });

  it('should return an empty string for empty or missing values', () => {
    expect(maskIdNumber('')).toBe('');
    expect(maskIdNumber(null)).toBe('');
    expect(maskIdNumber(undefined)).toBe('');
  });

  it('should trim surrounding whitespace before masking', () => {
    expect(maskIdNumber('  A123456789  ')).toBe('A******789');
    expect(maskIdNumber('   ')).toBe('');
  });
});
