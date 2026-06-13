'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import AuthFailNotice from '@/components/AuthFailNotice';
import SkeletonCard from '@/components/Skeleton';
import Navbar from '@/components/Navbar';
import Spinner from '@/components/Spinner';
import { api, normalizeApiError } from '@/lib/api';
import { CheckinItem, CheckinsResponse, continueHref, statusLabel } from '@/lib/checkins';
import { isDevPreviewToken } from '@/lib/devPreview';

const PAGE_SIZE = 20;
type Tab = 'all' | 'completed' | 'draft';

const tabs: Array<{ value: Tab; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'completed', label: '已发布' },
  { value: 'draft', label: '草稿' },
];

function HistoryContent() {
  const params = useSearchParams();
  const initialTab = (params.get('tab') as Tab) || 'all';
  const [activeTab, setActiveTab] = useState<Tab>(tabs.some((tab) => tab.value === initialTab) ? initialTab : 'all');
  const [items, setItems] = useState<CheckinItem[]>([]);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [isAuthError, setIsAuthError] = useState(false);

  const buildPath = useCallback((tab: Tab, nextOffset: number) => {
    const query = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(nextOffset),
    });
    if (tab !== 'all') query.set('status_filter', tab);
    return `/api/my/checkins?${query.toString()}`;
  }, []);

  const load = useCallback((tab: Tab, nextOffset: number, append = false, isRetry = false) => {
    // Dev preview has no backend session — show the empty state, not a 401.
    if (isDevPreviewToken(localStorage.getItem('token'))) {
      setLoading(false);
      return;
    }
    if (!append) {
      setLoading(true);
      if (!isRetry) {
        setError('');
        setIsAuthError(false);
      }
    } else {
      setLoadingMore(true);
    }
    api.get<CheckinsResponse>(buildPath(tab, nextOffset))
      .then((data) => {
        setItems((prev) => append ? [...prev, ...data.checkins] : data.checkins);
        setOffset(nextOffset + data.checkins.length);
        setHasMore(data.checkins.length === PAGE_SIZE);
        setError('');
        setIsAuthError(false);
      })
      .catch((e: unknown) => {
        const { message, is401 } = normalizeApiError(e, '历史记录加载失败');
        if (!append) setIsAuthError(is401);
        setError(message);
      })
      .finally(() => {
        setLoading(false);
        setLoadingMore(false);
      });
  }, [buildPath]);

  useEffect(() => {
    load(activeTab, 0, false);
  }, [activeTab, load]);

  function switchTab(tab: Tab) {
    if (tab === activeTab) return;
    setItems([]);
    setOffset(0);
    setHasMore(false);
    setActiveTab(tab);
  }

  return (
    <div className="sf-shell">
      <section className="sf-card sf-rise mb-5 p-6 md:p-8">
        <span className="sf-eyebrow">历史稿件</span>
        <h1 className="sf-display mt-4 text-[36px] font-bold leading-tight text-[var(--ink)]">你的每一次表达轨迹</h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--ink-soft)]">
          已发布、待发布和中断的内容都可以在这里回看。
        </p>
      </section>

      <div className="sf-rise sf-rise-1 mb-4 flex rounded-full border border-[var(--border)] bg-white/60 p-1">
        {tabs.map((tab) => (
          <button
            key={tab.value}
            onClick={() => switchTab(tab.value)}
            className={`flex-1 rounded-full px-4 py-2 text-sm transition ${
              activeTab === tab.value
                ? 'bg-[var(--ink)] text-white'
                : 'text-[var(--ink-muted)] hover:text-[var(--ink)]'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {isAuthError ? (
        <AuthFailNotice message="登录状态异常，无法加载历史记录。" />
      ) : error && (
        <div className="sf-note-card mb-4 px-4 py-3 text-sm text-[var(--danger)]">
          <p>{error}</p>
          <button
            onClick={() => load(activeTab, 0, false, true)}
            disabled={loading}
            className="mt-2 text-xs font-semibold text-primary-dark underline disabled:opacity-50"
          >
            {loading ? '重新加载中...' : '重新加载'}
          </button>
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <SkeletonCard key={i} height="h-32" />
          ))}
        </div>
      ) : items.length > 0 ? (
        <div className="space-y-3">
          {items.map((item) => (
            <Link key={item.id} href={continueHref(item)} className="sf-card block p-4 transition hover:border-[var(--border-strong)]">
              <div className="mb-2 flex items-center justify-between gap-3">
                <span className="text-xs text-[var(--ink-muted)]">{item.date}</span>
                <span className="sf-pill">{statusLabel(item.status)}</span>
              </div>
              <h2 className="text-base font-semibold leading-7 text-[var(--ink)]">{item.topic}</h2>
              {item.topic_source && <p className="mt-1 text-xs text-[var(--ink-muted)]">来源：{item.topic_source}</p>}
              {item.content && <p className="mt-3 line-clamp-3 text-sm leading-6 text-[var(--ink-soft)]">{item.content}</p>}
            </Link>
          ))}

          {hasMore && (
            <button
              onClick={() => load(activeTab, offset, true)}
              disabled={loadingMore}
              className="sf-btn-secondary w-full"
            >
              {loadingMore ? '加载中...' : '加载更多'}
            </button>
          )}
        </div>
      ) : (
        <div className="sf-card px-5 py-10 text-center">
          <p className="sf-display text-2xl font-semibold text-[var(--ink)]">
            {activeTab === 'completed' ? '还没有已发布的内容' : activeTab === 'draft' ? '草稿箱是空的' : '还没有创作记录'}
          </p>
          <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">从今日热点开始，写下第一条内容。</p>
          <Link href="/topics" className="sf-btn-primary mt-5">去写作</Link>
        </div>
      )}
    </div>
  );
}

export default function HistoryPage() {
  return (
    <ProtectedRoute>
      <Suspense fallback={<div className="flex min-h-screen items-center justify-center"><Spinner /></div>}>
        <HistoryContent />
      </Suspense>
      <Navbar />
    </ProtectedRoute>
  );
}
