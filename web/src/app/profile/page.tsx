'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import ProtectedRoute from '@/components/ProtectedRoute';
import Navbar from '@/components/Navbar';
import { api, getErrorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { CheckinItem, CheckinsResponse, continueHref, statusLabel } from '@/lib/checkins';

interface RedeemResponse {
  item: string;
  cost: number;
  diamonds: number;
  streak_freezes: number;
}

const FREEZE_COST = 5;

function ProfileContent() {
  const { user, logout, refreshUser } = useAuth();
  const [recent, setRecent] = useState<CheckinItem[]>([]);
  const [draftCount, setDraftCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [redeeming, setRedeeming] = useState(false);
  const [redeemNote, setRedeemNote] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  const redeemFreeze = useCallback(async () => {
    setRedeeming(true);
    setRedeemNote(null);
    try {
      const res = await api.post<RedeemResponse>('/api/redeem', { item: 'streak_freeze' });
      await refreshUser();
      setRedeemNote({ kind: 'ok', text: `兑换成功，现在有 ${res.streak_freezes} 张保护卡` });
    } catch (err) {
      setRedeemNote({ kind: 'error', text: getErrorMessage(err, '兑换失败，请稍后重试') });
    } finally {
      setRedeeming(false);
    }
  }, [refreshUser]);

  const loadProfileLists = useCallback(() => {
    setLoading(true);
    setLoadError(false);
    Promise.all([
      api.get<CheckinsResponse>('/api/my/checkins?limit=5&offset=0'),
      api.get<CheckinsResponse>('/api/my/checkins?status_filter=draft&limit=1&offset=0'),
    ])
      .then(([recentData, draftData]) => {
        setRecent(recentData.checkins);
        setDraftCount(draftData.draft_count);
      })
      .catch(() => {
        setLoadError(true);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => loadProfileLists(), [loadProfileLists]);

  if (!user) return null;

  return (
    <div className="sf-shell md:max-w-4xl xl:max-w-4xl">
      <section className="sf-card mb-5 p-6 md:p-8">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <span className="sf-eyebrow">我的内容</span>
            <h1 className="sf-display mt-4 text-[36px] font-bold leading-tight text-[var(--ink)]">管理你的发文记录</h1>
          </div>
          <button onClick={logout} className="sf-pill hover:border-[var(--danger)] hover:text-[var(--danger)]">
            退出
          </button>
        </div>
        <p className="max-w-2xl text-sm leading-7 text-[var(--ink-soft)]">
          这里保留草稿、历史稿件和设置入口，方便回到任意一篇内容。
        </p>
      </section>

      {user.gamification_enabled && (
        <section className="sf-card mb-5 p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="sf-eyebrow">奖励</p>
              <h2 className="sf-display mt-2 text-2xl font-semibold text-[var(--ink)]">连胜保护卡</h2>
              <p className="mt-2 max-w-md text-sm leading-6 text-[var(--ink-soft)]">
                断签当天自动消耗一张，连胜不归零。用攒下的钻石兑换，让积分不再是死数字。
              </p>
            </div>
            <div className="shrink-0 text-right">
              <p className="text-sm font-medium text-[var(--ink-soft)]">💎 {user.diamonds}</p>
              <p className="mt-1 text-sm font-medium text-sky-700">🧊 {user.streak_freezes} 张</p>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              onClick={redeemFreeze}
              disabled={redeeming || user.diamonds < FREEZE_COST}
              className="sf-btn-primary min-h-10 px-5 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {redeeming ? '兑换中…' : `用 ${FREEZE_COST} 💎 兑换一张`}
            </button>
            {user.diamonds < FREEZE_COST && (
              <span className="text-xs text-[var(--ink-muted)]">钻石不足，多发几天就够了</span>
            )}
          </div>
          {redeemNote && (
            <p
              className={`mt-3 text-sm ${redeemNote.kind === 'ok' ? 'text-emerald-700' : 'text-[var(--danger)]'}`}
            >
              {redeemNote.text}
            </p>
          )}
        </section>
      )}

      <div className="mb-5 grid gap-3 md:grid-cols-3">
        <Link href="/history?tab=completed" className="sf-card block p-5 transition hover:border-[var(--border-strong)]">
          <p className="sf-eyebrow">稿件</p>
          <h2 className="sf-display mt-2 text-2xl font-semibold text-[var(--ink)]">我的稿件</h2>
          <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">查看已经发布或确认过的内容。</p>
        </Link>
        <Link href="/drafts" className="sf-card block p-5 transition hover:border-[var(--border-strong)]">
          <div className="flex items-center justify-between gap-2">
            <p className="sf-eyebrow">草稿</p>
            <span className="sf-pill">{loadError ? '加载失败' : draftCount > 0 ? `${draftCount} 篇` : '空'}</span>
          </div>
          <h2 className="sf-display mt-2 text-2xl font-semibold text-[var(--ink)]">草稿箱</h2>
          <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">继续中断的创作。</p>
        </Link>
        <Link href="/settings" className="sf-card block p-5 transition hover:border-[var(--border-strong)]">
          <p className="sf-eyebrow">设置</p>
          <h2 className="sf-display mt-2 text-2xl font-semibold text-[var(--ink)]">发布设置</h2>
          <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">管理 API Key 和提醒时间。</p>
        </Link>
      </div>

      <section>
        <div className="mb-3 flex items-center justify-between px-1">
          <div>
            <p className="sf-eyebrow">最近创作</p>
            <h2 className="sf-display mt-1 text-2xl font-semibold text-[var(--ink)]">最近打开过的内容</h2>
          </div>
          <Link href="/history" className="text-xs font-medium text-primary-dark">全部</Link>
        </div>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-24 animate-pulse rounded-2xl bg-white/60" />
            ))}
          </div>
        ) : loadError ? (
          <div className="sf-note-card px-5 py-6">
            <p className="text-sm font-semibold text-[var(--ink)]">最近创作加载失败</p>
            <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">没有把错误当作空记录。请稍后重试。</p>
            <button onClick={loadProfileLists} className="sf-btn-secondary mt-4 min-h-10 px-4">
              重新加载
            </button>
          </div>
        ) : recent.length > 0 ? (
          <div className="space-y-3">
            {recent.map((item) => (
              <Link key={item.id} href={continueHref(item)} className="sf-card block p-4 transition hover:border-[var(--border-strong)]">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <span className="text-xs text-[var(--ink-muted)]">{item.date}</span>
                  <span className="sf-pill">{statusLabel(item.status)}</span>
                </div>
                <h3 className="text-base font-semibold leading-7 text-[var(--ink)]">{item.topic}</h3>
                {item.content && <p className="mt-2 line-clamp-2 text-sm leading-6 text-[var(--ink-soft)]">{item.content}</p>}
              </Link>
            ))}
          </div>
        ) : (
          <div className="sf-card px-5 py-8 text-center">
            <p className="sf-display text-2xl font-semibold text-[var(--ink)]">还没有创作记录</p>
            <Link href="/topics" className="sf-btn-primary mt-5">去写作</Link>
          </div>
        )}
      </section>
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
