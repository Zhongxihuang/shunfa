'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import ProtectedRoute from '@/components/ProtectedRoute';
import Navbar from '@/components/Navbar';
import SkeletonCard from '@/components/Skeleton';
import { api, ApiError } from '@/lib/api';
import { CheckinItem, CheckinsResponse, continueHref, statusLabel } from '@/lib/checkins';
import { useAuth } from '@/lib/auth';
import { isDevPreviewToken } from '@/lib/devPreview';

function Dashboard() {
  const { user, apiKeyConfigured, logout } = useAuth();
  const [recent, setRecent] = useState<CheckinItem[]>([]);
  const [drafts, setDrafts] = useState<CheckinItem[]>([]);
  const [draftCount, setDraftCount] = useState(0);
  const [loadingLists, setLoadingLists] = useState(true);
  const [listError, setListError] = useState(false);
  const [listAuthError, setListAuthError] = useState(false);

  // AuthProvider already calls refreshUser() on mount (auth.tsx); the cached
  // user flows into this component via the context, so the dashboard does not
  // need a second /api/user_status call.
  const loadDashboardLists = useCallback(() => {
    // Dev preview has no real backend session — show the empty states instead
    // of letting the 401 surface as a scary auth banner during UI demos.
    if (isDevPreviewToken(localStorage.getItem('token'))) {
      setLoadingLists(false);
      return;
    }
    let cancelled = false;
    setLoadingLists(true);
    setListAuthError(false);
    Promise.all([
      api.get<CheckinsResponse>('/api/my/checkins?limit=3&offset=0'),
      api.get<CheckinsResponse>('/api/my/checkins?status_filter=draft&limit=3&offset=0'),
    ])
      .then(([recentData, draftData]) => {
        if (cancelled) return;
        setRecent(recentData.checkins);
        setDrafts(draftData.checkins);
        setDraftCount(draftData.draft_count);
        setListError(false);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setListAuthError(e instanceof ApiError && e.status === 401);
        setListError(true);
      })
      .finally(() => {
        if (!cancelled) setLoadingLists(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => loadDashboardLists(), [loadDashboardLists]);

  if (!user) return null;

  return (
    <div className="sf-shell">
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem] xl:grid-cols-[minmax(0,1fr)_24rem]">
        <main className="min-w-0">
          <section className="sf-card sf-rise mb-5 p-6 md:p-8">
            <div className="mb-5 flex items-start justify-between gap-3">
              <span className="sf-eyebrow">顺发</span>
              <span className="sf-pill sf-pill-accent">{user.today_completed ? '今日已发布' : '今日待发'}</span>
            </div>
            <h1 className="sf-display text-[40px] font-bold leading-tight text-[var(--ink)] md:max-w-2xl md:text-[64px] md:leading-none">
              {user.today_completed ? '今天已经发出一条' : '今天，先发一条'}
            </h1>
            <p className="mt-4 max-w-xl text-sm leading-7 text-[var(--ink-soft)]">
              选一个热点，形成一个判断。草稿可以回来继续，历史稿件也会一直保留。
            </p>
            {user.gamification_enabled && (
              <div className="mt-5 flex flex-wrap gap-3">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-orange-50 px-3 py-1.5 text-sm font-medium text-orange-700">
                  🔥 {user.streak > 0 ? `已连更 ${user.streak} 天` : '今天开始第一天'}
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-full bg-yellow-50 px-3 py-1.5 text-sm font-medium text-yellow-700">
                  ⭐ {user.points} 积分
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-full bg-gray-100 px-3 py-1.5 text-sm font-medium text-gray-600">
                  Lv.{user.level}
                </span>
                {user.streak_freezes > 0 && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-sky-50 px-3 py-1.5 text-sm font-medium text-sky-700">
                    🧊 {user.streak_freezes} 张保护卡
                  </span>
                )}
              </div>
            )}
            {user.reminder_needed && !user.today_completed && (
              <div className="mt-4 rounded-xl bg-amber-50 border border-amber-200 px-4 py-2.5 text-sm text-amber-800">
                今天还没发，继续连胜的话现在可以开始 →
              </div>
            )}
            <div className="mt-6 flex flex-col gap-3 sm:flex-row">
              <Link href="/topics" className="sf-btn-primary flex-1">
                开始今日写作
              </Link>
              <Link href="/drafts" className="sf-btn-secondary flex-1">
                查看草稿箱
              </Link>
            </div>
          </section>

          {user && !apiKeyConfigured && (
            <div className="sf-note-card mb-4 px-4 py-3">
              <p className="text-sm font-semibold text-[var(--ink)]">还差一步：配置 DeepSeek API Key</p>
              <p className="mt-1 text-xs leading-5 text-[var(--ink-soft)]">AI 选题、深挖和起稿需要可用 Key。</p>
              <Link href="/settings" className="mt-2 inline-block text-xs font-semibold text-primary-dark underline">
                前往设置
              </Link>
            </div>
          )}

          <section className="sf-rise sf-rise-2 mb-5">
            {listError && (
              <div className="mb-3 flex items-center justify-between rounded-xl bg-white/50 px-4 py-2 text-xs text-[var(--ink-muted)]">
                {listAuthError ? (
                  <>
                    <span>登录状态异常，无法加载数据</span>
                    <button onClick={logout} className="font-medium text-primary-dark underline">重新登录</button>
                  </>
                ) : (
                  <>
                    <span>内容加载失败，可能是网络问题</span>
                    <button
                      onClick={loadDashboardLists}
                      disabled={loadingLists}
                      className="font-medium text-primary-dark underline disabled:opacity-50"
                    >
                      {loadingLists ? '重试中...' : '重试'}
                    </button>
                  </>
                )}
              </div>
            )}
            <div className="mb-3 flex items-center justify-between px-1">
              <div>
                <p className="sf-eyebrow">最近创作</p>
                <h2 className="sf-display mt-1 text-2xl font-semibold text-[var(--ink)]">继续看你的发文记录</h2>
              </div>
              <Link href="/history" className="text-xs font-medium text-primary-dark">全部</Link>
            </div>

            {loadingLists ? (
              <div className="grid gap-3 md:grid-cols-3">
                {[1, 2, 3].map((i) => (
                  <SkeletonCard key={i} height="h-32" />
                ))}
              </div>
            ) : recent.length > 0 ? (
              <div className="grid gap-3 md:grid-cols-3">
                {recent.map((item) => (
                  <Link key={item.id} href={continueHref(item)} className="sf-card block p-4 transition hover:border-[var(--border-strong)]">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <span className="text-xs text-[var(--ink-muted)]">{item.date}</span>
                      <span className="sf-pill">{statusLabel(item.status)}</span>
                    </div>
                    <h3 className="line-clamp-2 text-sm font-semibold leading-6 text-[var(--ink)]">{item.topic}</h3>
                    {item.content && (
                      <p className="mt-2 line-clamp-3 text-xs leading-5 text-[var(--ink-soft)]">{item.content}</p>
                    )}
                  </Link>
                ))}
              </div>
            ) : (
              <div className="sf-card px-5 py-8 text-center">
                <p className="sf-display text-2xl font-semibold text-[var(--ink)]">还没有创作记录</p>
                <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">从今日热点开始写第一条。</p>
              </div>
            )}
          </section>
        </main>

        <aside className="sf-rise sf-rise-3 lg:sticky lg:top-24 lg:self-start">
          <section className="sf-card mb-5 p-5">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="sf-display text-2xl font-semibold text-[var(--ink)]">草稿箱</h2>
              <span className="sf-pill">{draftCount > 0 ? `${draftCount} 篇` : '空'}</span>
            </div>
            {drafts.length > 0 ? (
              <div className="space-y-3">
                {drafts.map((item) => (
                  <Link key={item.id} href={continueHref(item)} className="block rounded-2xl border border-[var(--border)] bg-white/50 p-3 transition hover:bg-white/70">
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <span className="text-xs text-[var(--ink-muted)]">{item.date}</span>
                      <span className="text-xs text-primary-dark">{statusLabel(item.status)}</span>
                    </div>
                    <p className="line-clamp-2 text-sm font-medium leading-6 text-[var(--ink)]">{item.topic}</p>
                  </Link>
                ))}
                <Link href="/drafts" className="sf-btn-secondary w-full">查看全部草稿</Link>
              </div>
            ) : (
              <div>
                <p className="mb-4 text-sm leading-6 text-[var(--ink-soft)]">没有中断的创作。新草稿会出现在这里。</p>
                <Link href="/topics" className="sf-btn-primary w-full">去选题</Link>
              </div>
            )}
          </section>

          <section className="sf-note-card p-5">
            <p className="sf-eyebrow">提醒</p>
            <p className="mt-2 text-sm leading-7 text-[var(--ink-soft)]">
              顺发现在聚焦发文闭环：选题、起稿、修改、发布、回看。
            </p>
          </section>
        </aside>
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
