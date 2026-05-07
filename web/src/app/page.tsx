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
    <div className="sf-shell">
      {showReminderToast && (
        <div className="fixed left-4 right-4 top-4 z-50 mx-auto max-w-md rounded-2xl bg-primary-dark px-4 py-3 text-sm text-white shadow-lg">
          该写今天的文章了
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem] xl:grid-cols-[minmax(0,1fr)_24rem]">
        <div>
          <section className="sf-card mb-5 p-6 md:p-8">
            <div className="mb-5 flex items-start justify-between gap-3">
              <span className="sf-eyebrow">今日待发</span>
              <span className="sf-pill sf-pill-accent">顺发</span>
            </div>
            <h1 className="sf-display text-[40px] font-bold leading-tight text-[var(--ink)] md:max-w-2xl md:text-[64px] md:leading-none">今天，先发一条</h1>
            <p className="mt-4 max-w-xl text-sm leading-7 text-[var(--ink-soft)]">
              从热点里挑一个判断，生成初稿，改到能发为止。
            </p>
          </section>

          {user && !apiKeyConfigured && (
            <div className="sf-note-card mb-4 px-4 py-3">
              <p className="text-sm font-semibold text-[var(--ink)]">还差一步：配置 DeepSeek API Key</p>
              <p className="mt-1 text-xs leading-5 text-[var(--ink-soft)]">AI 选题、深挖和起稿需要可用 Key。</p>
              <Link
                href="/settings"
                className="mt-2 inline-block text-xs font-semibold text-primary-dark underline"
              >
                前往设置
              </Link>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4 mb-6">
            <div className="sf-card p-4">
              <StreakBadge streak={user.streak} longestStreak={user.longest_streak} />
            </div>
            <div className="sf-card p-4">
              <DiamondDisplay diamonds={user.diamonds} />
            </div>
          </div>
        </div>

        <div className="lg:sticky lg:top-24 lg:self-start">
          <div className="sf-card mb-5 p-4">
            <LevelProgress level={user.level} points={user.points} />
          </div>

          <div className="sf-card p-5">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="sf-display text-2xl font-semibold text-[var(--ink)]">今日动作</h2>
              <span className="sf-pill">{user.today_completed ? '已完成' : '待开始'}</span>
            </div>
            {user.today_completed ? (
              <div className="flex items-center gap-2">
                <span className="h-3 w-3 rounded-full bg-primary"></span>
                <span className="text-sm font-medium text-primary-dark">今日已打卡</span>
              </div>
            ) : (
              <div>
                <p className="mb-4 text-sm leading-6 text-[var(--ink-soft)]">今天还没写文章，从今日热点里选一条，先生成一个能改的初稿。</p>
                <Link
                  href="/topics"
                  className="sf-btn-primary w-full"
                >
                  开始今日写作
                </Link>
              </div>
            )}
          </div>
        </div>
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
