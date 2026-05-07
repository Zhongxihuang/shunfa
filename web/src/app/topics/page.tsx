'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import TopicCard from '@/components/TopicCard';
import { api } from '@/lib/api';

interface TopicItem {
  topic: string;
  batch_id: string;
}

interface HotTopicItem {
  id: number;
  title: string;
  summary: string;
  source: string;
  url: string;
  published_at?: string | null;
  score: number;
  category: string;
  ai_angle: string;
  ai_counter_angle: string;
}

function TopicsContent() {
  const router = useRouter();
  const [topics, setTopics] = useState<TopicItem[]>([]);
  const [hotTopics, setHotTopics] = useState<HotTopicItem[]>([]);
  const [refreshCount, setRefreshCount] = useState(0);
  const [maxRefreshes, setMaxRefreshes] = useState(3);
  const [loading, setLoading] = useState(false);
  const [hotLoading, setHotLoading] = useState(true);
  const [aiLoaded, setAiLoaded] = useState(false);
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);
  const [selectedHotTopicId, setSelectedHotTopicId] = useState<number | null>(null);
  const [customTopic, setCustomTopic] = useState('');
  const [showCustom, setShowCustom] = useState(false);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadHotTopics();
  }, []);

  async function loadHotTopics() {
    setHotLoading(true);
    setError('');
    try {
      const data = await api.get<{ date: string; topics: HotTopicItem[] }>('/api/hot_topics/today');
      setHotTopics(data.topics);
    } catch (e: unknown) {
      const err = e as { data?: { detail?: string } };
      setError(err?.data?.detail ?? '获取今日热点失败');
    } finally {
      setHotLoading(false);
    }
  }

  async function loadTopics() {
    setLoading(true);
    setError('');
    try {
      const data = await api.post<{ topics: TopicItem[]; refresh_count: number; max_refreshes: number }>('/api/daily_topics');
      setTopics(data.topics);
      setRefreshCount(data.refresh_count);
      setMaxRefreshes(data.max_refreshes);
      setAiLoaded(true);
    } catch (e: unknown) {
      const err = e as { data?: { detail?: string } };
      setError(err?.data?.detail ?? '获取选题失败');
    } finally {
      setLoading(false);
    }
  }

  function handleRefresh() {
    if (refreshCount >= maxRefreshes) {
      setError('今日换题次数已用完');
      return;
    }
    setSelectedTopic(null);
    loadTopics();
  }

  function handleConfirmHotTopic() {
    if (!selectedHotTopicId) {
      setError('请选择一个热点');
      return;
    }
    router.push(`/compose?topic_id=${selectedHotTopicId}`);
  }

  async function handleConfirm() {
    const topic = selectedTopic ?? customTopic.trim();
    if (!topic) {
      setError('请选择或输入一个选题');
      return;
    }

    const selectedCard = topics.find((t) => t.topic === selectedTopic);
    const body = selectedCard
      ? { topic, batch_id: selectedCard.batch_id }
      : { topic };

    setSubmitting(true);
    try {
      const data = await api.post<{ checkin_id: number }>('/api/select_topic', body);
      router.push(`/discuss?checkin_id=${data.checkin_id}&topic=${encodeURIComponent(topic)}`);
    } catch (e: unknown) {
      const err = e as { data?: { detail?: string } };
      setError(err?.data?.detail ?? '选题失败');
      setSubmitting(false);
    }
  }

  return (
    <div className="sf-shell">
      <div className="mb-4 flex items-center gap-3">
        <button
          onClick={() => router.back()}
          aria-label="返回上一页"
          className="sf-btn-secondary h-10 min-h-10 w-10 px-0"
        >
          ←
        </button>
        <span className="sf-eyebrow">返回</span>
      </div>

      {error && (
        <div className="sf-note-card mb-4 px-4 py-3 text-sm text-[var(--danger)]">
          <p>{error}</p>
          {error.includes('API Key') && (
            <Link href="/settings" className="mt-1 inline-block font-medium text-primary-dark underline">
              前往设置页面配置
            </Link>
          )}
        </div>
      )}

      <section className="sf-card mb-5 p-6">
        <div className="mb-5 flex items-start justify-between gap-3">
          <span className="sf-eyebrow">今日选题</span>
          <span className="sf-pill sf-pill-accent">原始来源已保留</span>
        </div>
        <h1 className="sf-display text-[36px] font-bold leading-tight text-[var(--ink)]">今天选一条就够了</h1>
        <p className="mt-4 text-sm leading-7 text-[var(--ink-soft)]">
          这些热点保留了标题、摘要、来源和原始链接。你只需要挑一条最想表达判断的。
        </p>
      </section>

      <div className="sf-page-grid">
        <section className="sf-page-main mb-5">
          <div className="mb-3 flex items-end justify-between px-1">
            <div>
              <p className="sf-eyebrow">热点列表</p>
              <h2 className="sf-display mt-1 text-2xl font-semibold text-[var(--ink)]">选一个热点直接开写</h2>
            </div>
            <button
              onClick={loadHotTopics}
              disabled={hotLoading}
              className="text-xs font-medium text-primary-dark disabled:opacity-40"
            >
              刷新
            </button>
          </div>

          {hotLoading ? (
            <div className="grid gap-3 md:grid-cols-2">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-36 animate-pulse rounded-2xl bg-[rgba(255,253,250,0.7)]" />
              ))}
            </div>
          ) : hotTopics.length > 0 ? (
            <div className="grid gap-3 md:grid-cols-2">
              {hotTopics.map((topic, index) => (
                <button
                  key={topic.id}
                  onClick={() => setSelectedHotTopicId(topic.id)}
                  className={`block min-h-40 w-full rounded-2xl border p-4 text-left shadow-sm transition ${
                    selectedHotTopicId === topic.id
                      ? 'border-primary bg-primary/5 shadow-primary/10'
                      : 'border-[var(--border)] bg-[var(--surface)] hover:border-[var(--border-strong)]'
                  }`}
                >
                  <div className="mb-2 flex items-start gap-3">
                    <span className="mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary-dark">
                      {index + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <h3 className="text-sm font-semibold leading-relaxed text-[var(--ink)]">{topic.title}</h3>
                      <p className="mt-1 text-xs text-[var(--ink-muted)]">{topic.source}</p>
                    </div>
                  </div>
                  {topic.summary && (
                    <p className="mb-2 line-clamp-3 text-xs leading-relaxed text-[var(--ink-soft)]">{topic.summary}</p>
                  )}
                  {topic.ai_angle && (
                    <p className="rounded-xl bg-primary/5 px-3 py-2 text-xs leading-relaxed text-primary-dark">
                      {topic.ai_angle}
                    </p>
                  )}
                </button>
              ))}
            </div>
          ) : (
            <div className="sf-card px-5 py-6 text-center">
              <p className="sf-display text-2xl font-semibold text-[var(--ink)]">今天的热点还没准备好</p>
              <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">可能是定时抓取还没跑，或者今天的 RSS 还没入库。你可以先重试一次，或使用 AI 选题。</p>
            </div>
          )}
        </section>

        <aside className="sf-page-side">
          {hotTopics.length > 0 && (
            <div className="sf-card mb-4 p-4">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="sf-display text-xl font-semibold text-[var(--ink)]">当前选择</h3>
                <span className="sf-pill">{selectedHotTopicId ? '已选中 1 条' : '还未选题'}</span>
              </div>
              <p className="mb-4 text-sm leading-6 text-[var(--ink-soft)]">确认后进入创作页，继续选择角度和平台。</p>
              <button
                onClick={handleConfirmHotTopic}
                disabled={!selectedHotTopicId}
                className="sf-btn-primary w-full"
              >
                就选这一条
              </button>
            </div>
          )}

          <div className="mb-4 flex items-center gap-3">
            <div className="flex-1 border-t border-[var(--border)]" />
            <span className="text-sm text-[var(--ink-muted)]">其他入口</span>
            <div className="flex-1 border-t border-[var(--border)]" />
          </div>

          {!aiLoaded && (
            <button
              onClick={loadTopics}
              disabled={loading}
              className="sf-btn-secondary mb-4 w-full"
            >
              {loading ? '生成中...' : '生成 AI 选题'}
            </button>
          )}

          {aiLoaded && (
            <>
              {loading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="h-20 animate-pulse rounded-2xl bg-[rgba(255,253,250,0.7)]" />
                  ))}
                </div>
              ) : (
                <div className="space-y-3 mb-4">
                  {topics.map((t, i) => (
                    <TopicCard
                      key={t.topic}
                      topic={t.topic}
                      index={i}
                      selected={selectedTopic === t.topic}
                      onSelect={(topic) => {
                        setSelectedTopic(topic);
                        setCustomTopic('');
                      }}
                    />
                  ))}
                </div>
              )}

              <button
                onClick={handleRefresh}
                disabled={loading || refreshCount >= maxRefreshes}
                className="sf-btn-secondary mb-4 w-full"
              >
                换一批（剩余 {maxRefreshes - refreshCount} 次）
              </button>
            </>
          )}

          <button
            onClick={() => setShowCustom(!showCustom)}
            className="mb-3 w-full rounded-full border border-dashed border-[var(--border-strong)] bg-white/50 py-3 text-sm text-[var(--ink-muted)] transition hover:bg-white/70"
          >
            {showCustom ? '收起自定义输入' : '自定义话题...'}
          </button>

          {showCustom && (
            <div className="mb-4">
              <div className="relative">
                <input
                  type="text"
                  maxLength={50}
                  value={customTopic}
                  onChange={(e) => {
                    setCustomTopic(e.target.value);
                    setSelectedTopic(null);
                  }}
                  placeholder="输入你的话题（最多 50 字）"
                  className="w-full rounded-2xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--ink)] focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[var(--ink-muted)]">
                  {customTopic.length}/50
                </span>
              </div>
            </div>
          )}

          <button
            onClick={handleConfirm}
            disabled={submitting || (!selectedTopic && !customTopic.trim())}
            className="sf-btn-primary w-full"
          >
            {submitting ? '跳转中...' : '开始写作'}
          </button>
        </aside>
      </div>
    </div>
  );
}

export default function TopicsPage() {
  return (
    <ProtectedRoute>
      <TopicsContent />
    </ProtectedRoute>
  );
}
