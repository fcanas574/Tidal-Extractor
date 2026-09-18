import { describe, it, expect } from 'vitest';
import {
  sliderToGain,
  gainToSlider,
  gainToDb,
  sliderToDb,
  formatDb,
  LOG_DB_RANGE,
  LOG_A,
} from './audioMath';

describe('audioMath psychoacoustic volume curve', () => {
  it('correctly sets the 60 dB dynamic range constants', () => {
    expect(LOG_DB_RANGE).toBe(60);
    expect(LOG_A).toBeCloseTo(0.001, 6);
  });

  it('handles boundary values for sliderToGain', () => {
    expect(sliderToGain(0)).toBe(0);
    expect(sliderToGain(-0.5)).toBe(0);
    expect(sliderToGain(1)).toBe(1);
    expect(sliderToGain(1.5)).toBe(1);
  });

  it('maps slider position 0.5 to exactly -30 dB (halfway across 60 dB range)', () => {
    const gainAtHalf = sliderToGain(0.5);
    const dbAtHalf = gainToDb(gainAtHalf);
    // Across a 60 dB range from -60 to 0, halfway is -30 dB
    expect(dbAtHalf).toBeCloseTo(-30, 2);
    expect(gainAtHalf).toBeCloseTo(10 ** (-30 / 20), 5);
  });

  it('provides continuous behavior at the 0.1 roll-off boundary', () => {
    const gainBelow = sliderToGain(0.099999);
    const gainAt = sliderToGain(0.1);
    const gainAbove = sliderToGain(0.100001);

    expect(gainBelow).toBeCloseTo(gainAt, 4);
    expect(gainAbove).toBeCloseTo(gainAt, 4);
  });

  it('smoothly reduces to 0 below 0.1 without sudden jumps', () => {
    const g0 = sliderToGain(0);
    const g02 = sliderToGain(0.02);
    const g05 = sliderToGain(0.05);
    const g08 = sliderToGain(0.08);
    const g10 = sliderToGain(0.1);

    expect(g0).toBe(0);
    expect(g02).toBeGreaterThan(g0);
    expect(g05).toBeGreaterThan(g02);
    expect(g08).toBeGreaterThan(g05);
    expect(g10).toBeGreaterThan(g08);
  });

  it('is monotonically increasing across the entire [0, 1] range', () => {
    let lastGain = -1;
    for (let i = 0; i <= 100; i++) {
      const x = i / 100;
      const g = sliderToGain(x);
      expect(g).toBeGreaterThanOrEqual(lastGain);
      lastGain = g;
    }
  });

  it('invertibility: gainToSlider reverses sliderToGain', () => {
    const testPoints = [0, 0.02, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 1];
    for (const p of testPoints) {
      const gain = sliderToGain(p);
      const inv = gainToSlider(gain);
      expect(inv).toBeCloseTo(p, 4);
    }
  });

  it('computes decibels correctly', () => {
    expect(gainToDb(1)).toBeCloseTo(0, 4);
    expect(gainToDb(0.1)).toBeCloseTo(-20, 4);
    expect(gainToDb(0.01)).toBeCloseTo(-40, 4);
    expect(gainToDb(0.001)).toBeCloseTo(-60, 4);
    expect(gainToDb(0)).toBe(-Infinity);
  });

  it('formats decibels human-readably', () => {
    expect(formatDb(0)).toBe('0.0 dB');
    expect(formatDb(-12.34)).toBe('-12.3 dB');
    expect(formatDb(-Infinity)).toBe('-inf dB');
    expect(formatDb(-120)).toBe('-inf dB');
  });

  it('sliderToDb gives expected perceptual levels', () => {
    expect(sliderToDb(1)).toBeCloseTo(0, 1);
    expect(sliderToDb(0.75)).toBeCloseTo(-15, 1);
    expect(sliderToDb(0.5)).toBeCloseTo(-30, 1);
    expect(sliderToDb(0.25)).toBeCloseTo(-45, 1);
    expect(sliderToDb(0)).toBe(-Infinity);
  });
});
