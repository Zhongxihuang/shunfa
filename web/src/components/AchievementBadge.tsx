interface Props {
  type: string;
  name: string;
  unlocked: boolean;
}

const ICONS: Record<string, string> = {
  first_checkin: '🌟',
  streak_3: '🔥',
  streak_7: '🚀',
  streak_30: '💫',
  points_100: '💰',
  points_500: '💎',
  level_3: '🎖️',
  level_5: '🏆',
};

export default function AchievementBadge({ type, name, unlocked }: Props) {
  const icon = ICONS[type] ?? '🏅';
  return (
    <div className={`flex flex-col items-center gap-1 p-3 rounded-xl ${unlocked ? 'bg-primary/10' : 'bg-gray-100 opacity-50'}`}>
      <span className="text-2xl">{icon}</span>
      <span className="text-xs text-center text-gray-700 leading-tight">{name}</span>
    </div>
  );
}
