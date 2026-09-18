/**
 * Audio volume mathematics based on human psychoacoustic perception.
 * Reference: Alva Majo - "El volumen no es lineal" (https://www.youtube.com/watch?v=MquQQX0Ak0k)
 * and Dr. Alexander Thomas (Dr. Lex) - "Programming Volume Controls" (https://www.dr-lex.be/info-stuff/volumecontrols.html)
 *
 * Human hearing perceives loudness logarithmically. A linear slider controlling linear amplitude
 * creates an unnatural response where 90% of the movement barely changes perceived loudness,
 * and quiet sounds are crammed into the first 5% of the slider.
 *
 * An exponential curve with 60 dB dynamic range (consumer audio standard) provides a smooth,
 * perceptually linear volume adjustment. A linear roll-off is applied below x = 0.1 to seamlessly
 * reach true silence (gain = 0) at x = 0.
 */

export const LOG_DB_RANGE = 60;
export const LOG_A = 1 / 10 ** (LOG_DB_RANGE / 20); // 0.001 (-60 dB)
export const LOG_B = Math.log(1 / LOG_A); // ln(1000) ~ 6.907755
export const LOG_ROLLOFF = 10 * LOG_A * Math.exp(LOG_B * 0.1);

/**
 * Converts a linear slider position x in [0, 1] to audio amplitude/gain in [0, 1].
 */
export function sliderToGain(x: number): number {
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  if (x < 0.1) {
    return x * LOG_ROLLOFF;
  }
  const gain = LOG_A * Math.exp(LOG_B * x);
  return Math.min(1, Math.max(0, gain));
}

/**
 * Converts an audio amplitude/gain in [0, 1] back to a slider position in [0, 1].
 */
export function gainToSlider(gain: number): number {
  if (gain <= 0) return 0;
  if (gain >= 1) return 1;
  const rolloffThreshold = 0.1 * LOG_ROLLOFF;
  if (gain < rolloffThreshold) {
    return Math.max(0, gain / LOG_ROLLOFF);
  }
  const x = Math.log(gain / LOG_A) / LOG_B;
  return Math.min(1, Math.max(0, x));
}

/**
 * Computes decibels relative to full scale (dBFS) for a given linear gain in [0, 1].
 */
export function gainToDb(gain: number): number {
  if (gain <= 0.000001) return -Infinity;
  return 20 * Math.log10(gain);
}

/**
 * Computes decibels for a given slider position x in [0, 1].
 */
export function sliderToDb(x: number): number {
  return gainToDb(sliderToGain(x));
}

/**
 * Formats decibels for display (e.g. "0.0 dB", "-12.0 dB", "-inf dB").
 */
export function formatDb(db: number): string {
  if (!Number.isFinite(db) || db <= -99) {
    return '-inf dB';
  }
  return `${db.toFixed(1)} dB`;
}
