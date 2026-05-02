'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import ProtectedRoute from '@/components/ProtectedRoute';
import Navbar from '@/components/Navbar';
import StreakBadge from '@/components/StreakBadge';
import DiamondDisplay from '@/components/DiamondDisplay';
import LevelProgress from '@/components/LevelProgress';
import { useAuth } from '@/lib/auth';

function Dashboard() {
  const { user, refreshUser, apiKeyConfigured } = useAuth();
  const [showReminderToast, setShowReminderToast] = useState(false);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  useEffect(() => {
    if (user?.reminder_needed) {
      setShowReminderToast(true);
      const t = setTimeout(() => setShowReminderToast(false), 4000);
      return () => clearTimeout(t);
    }
  }, [user?.reminder_needed]);

  if (!user) return null;

  return (
    <div className="max-w-md mx-auto px-4 pt-6 pb-24">
      {showReminderToast && (
        <div className="fixed top-4 left-4 right-4 max-w-md mx-auto bg-primary text-white px-4 py-3 rounded-xl shadow-lg z-50 text-sm">
          该写今天的文章啦！🔔
        </div>
      )}

      <h1 className="text-xl font-bold text-gray-900 mb-4">顺发</h1>

      {user && !apiKeyConfigured && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 mb-4">
          <p className="text-sm font-medium text-amber-800">还差一步：配置 DeepSeek API Key</p>
          <p className="text-xs text-amber-700 mt-0.5">AI 选题和讨论功能需要你自己的 Key。</p>
          <Link
            href="/settings"
            className="mt-2 inline-block text-xs font-medium text-amber-900 underline"
          >
            前往设置 →
          </Link>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="bg-white rounded-2xl p-4 shadow-sm">
          <StreakBadge streak={user.streak} longestStreak={user.longest_streak} />
        </div>
        <div className="bg-white rounded-2xl p-4 shadow-sm">
          <DiamondDisplay diamonds={user.diamonds} />
        </div>
      </div>

      <div className="bg-white rounded-2xl p-4 shadow-sm mb-6">
        <LevelProgress level={user.level} points={user.points} />
      </div>

      <div className="bg-white rounded-2xl p-5 shadow-sm">
        <h2 className="font-semibold text-gray-800 mb-3">今日状态</h2>
        {user.today_completed ? (
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-primary"></span>
            <span className="text-primary font-medium text-sm">今日已打卡 ✓</span>
          </div>
        ) : (
          <div>
            <p className="text-gray-500 text-sm mb-3">今天还没写文章，快来开始吧！</p>
            <Link
              href="/topics"
              className="block w-full text-center py-3 bg-primary text-white rounded-xl font-medium hover:bg-primary-dark transition-colors"
            >
              开始今天的选题 →
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}

export default function HomePage() {
  return (
    <ProtectedRoute>
      <Dashboard />
      <Navbar />
    </ProtectedRoute>
  );
}
