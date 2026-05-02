import { getLevelProgress, getNextLevelPoints, LEVEL_NAMES } from '@/lib/constants';

interface Props {
  level: number;
  points: number;
}

export default function LevelProgress({ level, points }: Props) {
  const progress = getLevelProgress(level, points);
  const nextPoints = getNextLevelPoints(level);
  const levelName = LEVEL_NAMES[level - 1] ?? '传奇';

  return (
    <div className="w-full">
      <div className="flex justify-between items-center mb-1">
        <span className="text-sm font-medium text-gray-700">Lv.{level} {levelName}</span>
        <span className="text-xs text-gray-500">
          {points} {nextPoints ? `/ ${nextPoints}` : ''} pts
        </span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2">
        <div
          className="bg-primary h-2 rounded-full transition-all duration-500"
          style={{ width: `${Math.min(progress, 100)}%` }}
        />
      </div>
    </div>
  );
}
