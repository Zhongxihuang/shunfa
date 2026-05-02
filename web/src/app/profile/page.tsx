'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import ProtectedRoute from '@/components/ProtectedRoute';
import Navbar from '@/components/Navbar';
import AchievementBadge from '@/components/AchievementBadge';
import { useAuth } from '@/lib/auth';
import { api } from '@/lib/api';
import { isDevPreviewToken } from '@/lib/devPreview';
import { LEVEL_NAMES } from '@/lib/constants';

interface Achievement {
  type: string;
  name: string;
  desc: string;
  unlocked_at: string | null;
}

function ProfileContent() {
  const { user, token, refreshUser, logout } = useAuth();
  const [achievements, setAchievements] = useState<Achievement[]>([]);

  useEffect(() => {
    refreshUser();
    if (isDevPreviewToken(token)) {
      setAchievements([]);
      return;
    }
    api.get<{ achievements: Achievement[]; total: number }>('/api/achievements').then((d) =>
      setAchievements(d.achievements)
    ).catch(() => setAchievements([]));
  }, [refreshUser, token]);

  if (!user) return null;

  const levelName = LEVEL_NAMES[user.level - 1] ?? '传奇';

  return (
    <div className="max-w-md mx-auto px-4 pt-6 pb-24">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-gray-900">个人</h1>
        <button onClick={logout} className="text-sm text-gray-400 hover:text-gray-600">
          退出
        </button>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-3 mb-6">
        {[
          { label: '连续天数', value: `${user.streak} 🔥` },
          { label: '最长连胜', value: `${user.longest_streak} 天` },
          { label: '总积分', value: `${user.points} pts` },
          { label: '当前等级', value: `Lv.${user.level} ${levelName}` },
        ].map((s) => (
          <div key={s.label} className="bg-white rounded-2xl p-4 shadow-sm">
            <div className="text-xl font-bold text-gray-800">{s.value}</div>
            <div className="text-xs text-gray-500 mt-1">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Diamonds */}
      <div className="bg-white rounded-2xl p-4 shadow-sm mb-6 flex items-center gap-3">
        <span className="text-3xl">💎</span>
        <div>
          <div className="text-2xl font-bold text-gray-800">{user.diamonds}</div>
          <div className="text-xs text-gray-500">钻石</div>
        </div>
      </div>

      {/* Achievements */}
      {achievements.length > 0 && (
        <div className="bg-white rounded-2xl p-4 shadow-sm mb-4">
          <h2 className="font-semibold text-gray-800 mb-3">成就</h2>
          <div className="grid grid-cols-4 gap-2">
            {achievements.map((a) => (
              <AchievementBadge
                key={a.type}
                type={a.type}
                name={a.name}
                unlocked={!!a.unlocked_at}
              />
            ))}
          </div>
        </div>
      )}

      <Link href="/settings" className="block text-center text-sm text-primary py-2">
        前往设置 →
      </Link>
    </div>
  );
}

export default function ProfilePage() {
  return (
    <ProtectedRoute>
      <ProfileContent />
      <Navbar />
    </ProtectedRoute>
  );
}
