export function normalizeQualityScoreForDisplay(value: unknown): number | null {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return null;
  }
  if (value >= 0 && value <= 1) {
    return Math.round(value * 100);
  }
  if (value > 1 && value <= 100) {
    return Math.round(value);
  }
  return null;
}
