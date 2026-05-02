interface Props {
  streak: number;
  longestStreak: number;
}

export default function StreakBadge({ streak, longestStreak }: Props) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-3xl">🔥</span>
      <div>
        <div className="text-2xl font-bold text-gray-800">{streak}</div>
        <div className="text-xs text-gray-500">连续 · 最长 {longestStreak} 天</div>
      </div>
    </div>
  );
}
