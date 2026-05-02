export const LEVEL_THRESHOLDS = [0, 100, 300, 700, 1500, 3100, 6300];

export const LEVEL_NAMES = ['新手', '初学者', '进阶者', '熟练者', '专家', '大师', '传奇'];

export function getLevelProgress(level: number, points: number): number {
  const idx = level - 1;
  const current = LEVEL_THRESHOLDS[idx] ?? 0;
  const next = LEVEL_THRESHOLDS[idx + 1];
  if (!next) return 100;
  return Math.round(((points - current) / (next - current)) * 100);
}

export function getNextLevelPoints(level: number): number | null {
  return LEVEL_THRESHOLDS[level] ?? null;
}
