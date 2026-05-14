'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import ProtectedRoute from '@/components/ProtectedRoute';
import Navbar from '@/components/Navbar';
import { api } from '@/lib/api';
import { CheckinItem, CheckinsResponse, continueHref, statusLabel } from '@/lib/checkins';

function DraftsContent() {
  const [drafts, setDrafts] = useState<CheckinItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  function loadDrafts() {
    setLoading(true);
    setError('');
    api.get<CheckinsResponse>('/api/my/checkins?status_filter=draft&limit=100&offset=0')
      .then((data) => setDrafts(data.checkins))
      .catch((e: unknown) => {
        const err = e as { data?: { detail?: string } };
        setError(err?.data?.detail ?? '草稿加载失败');
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadDrafts();
  }, []);

  return (
    <div className="sf-shell">
      <section className="sf-card mb-5 p-6 md:p-8">
        <div className="mb-4 flex items-center justify-between gap-3">
          <span className="sf-eyebrow">草稿箱</span>
          <Link href="/topics" className="sf-pill sf-pill-accent">新建</Link>
        </div>
        <h1 className="sf-display text-[36px] font-bold leading-tight text-[var(--ink)]">中断的创作，随时继续</h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--ink-soft)]">
          选题、讨论中、待发布和待确认的内容都会留在这里。
        </p>
      </section>

      {error && (
        <div className="sf-note-card mb-4 px-4 py-3 text-sm text-[var(--danger)]">
          <p>{error}</p>
          <button onClick={loadDrafts} className="mt-2 text-xs font-semibold text-primary-dark underline">重新加载</button>
        </div>
      )}

      {loading ? (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-40 animate-pulse rounded-2xl bg-white/60" />
          ))}
        </div>
      ) : drafts.length > 0 ? (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {drafts.map((item) => (
            <article key={item.id} className="sf-card p-4">
              <div className="mb-3 flex items-center justify-between gap-2">
                <span className="text-xs text-[var(--ink-muted)]">{item.date}</span>
                <span className="sf-pill">{statusLabel(item.status)}</span>
              </div>
              <h2 className="line-clamp-2 text-base font-semibold leading-7 text-[var(--ink)]">{item.topic}</h2>
              {item.topic_source && <p className="mt-1 text-xs text-[var(--ink-muted)]">来源：{item.topic_source}</p>}
              {item.content && <p className="mt-3 line-clamp-4 text-sm leading-6 text-[var(--ink-soft)]">{item.content}</p>}
              <Link href={continueHref(item)} className="sf-btn-primary mt-4 w-full">
                继续
              </Link>
            </article>
          ))}
        </div>
      ) : (
        <div className="sf-card px-5 py-10 text-center">
          <p className="sf-display text-2xl font-semibold text-[var(--ink)]">草稿箱是空的</p>
          <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">所有创作都已完成，或者还没有开始新的草稿。</p>
          <Link href="/topics" className="sf-btn-primary mt-5">去选题</Link>
        </div>
      )}
    </div>
  );
}

export default function DraftsPage() {
  return (
    <ProtectedRoute>
      <DraftsContent />
      <Navbar />
    </ProtectedRoute>
  );
}
