'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import { api, getErrorMessage } from '@/lib/api';

type Platform = 'xiaohongshu' | 'twitter' | 'weibo' | 'wechat_short' | 'generic';

interface HotTopicDetail {
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

interface HotTopicAnalysis {
  opportunities: string[];
  risks: string[];
  recommended_frame: string;
  angles: string[];
}

const PLATFORM_OPTIONS: Array<{ value: Platform; label: string; hint: string }> = [
  { value: 'xiaohongshu', label: '小红书', hint: '短段落、口语、有观点' },
  { value: 'twitter', label: '推特', hint: '短句、单点判断' },
  { value: 'weibo', label: '微博', hint: '热点短评、开门见山' },
  { value: 'wechat_short', label: '公众号短消息', hint: '背景、判断、启发' },
  { value: 'generic', label: '通用版', hint: '中性、方便复用' },
];

const LAST_PLATFORM_KEY = 'shunfa_last_platform';

function getSavedPlatform(): Platform {
  if (typeof window === 'undefined') return 'xiaohongshu';
  const saved = localStorage.getItem(LAST_PLATFORM_KEY);
  return PLATFORM_OPTIONS.some((option) => option.value === saved)
    ? (saved as Platform)
    : 'xiaohongshu';
}

function ComposeContent() {
  const router = useRouter();
  const params = useSearchParams();
  const topicId = parseInt(params.get('topic_id') ?? '0', 10);

  const [topic, setTopic] = useState<HotTopicDetail | null>(null);
  const [analysis, setAnalysis] = useState<HotTopicAnalysis | null>(null);
  const [platform, setPlatform] = useState<Platform>('xiaohongshu');
  const [selectedAngle, setSelectedAngle] = useState('');
  const [loading, setLoading] = useState(true);
  const [digging, setDigging] = useState(false);
  const [submitting, setSubmitting] = useState<'quick' | 'deep' | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    setPlatform(getSavedPlatform());
  }, []);

  useEffect(() => {
    if (!topicId) {
      setLoading(false);
      setError('缺少热点 ID，请返回重新选择');
      return;
    }

    setLoading(true);
    setError('');
    api.get<HotTopicDetail>(`/api/hot_topics/${topicId}`)
      .then((data) => {
        setTopic(data);
        setSelectedAngle(data.ai_angle || data.ai_counter_angle || `我更关心「${data.title}」背后的行业信号`);
      })
      .catch((e: unknown) => {
        setError(getErrorMessage(e, '热点详情加载失败'));
      })
      .finally(() => setLoading(false));
  }, [topicId]);

  function handlePlatformChange(next: Platform) {
    setPlatform(next);
    localStorage.setItem(LAST_PLATFORM_KEY, next);
  }

  const angleOptions = useMemo(() => {
    if (!topic) return [];
    const values = [
      topic.ai_angle,
      topic.ai_counter_angle,
      analysis?.recommended_frame,
      ...(analysis?.angles ?? []),
    ].filter(Boolean) as string[];
    return Array.from(new Set(values));
  }, [topic, analysis]);

  async function createCheckin() {
    if (!topic) throw new Error('缺少热点信息');
    return api.post<{ checkin_id: number }>('/api/select_topic', {
      topic: topic.title,
      hot_topic_id: topic.id,
      selected_angle: selectedAngle,
      platform,
    });
  }

  async function handleDigDeeper() {
    if (!topic || digging) return;
    setDigging(true);
    setError('');
    try {
      const data = await api.postGeneration<HotTopicAnalysis>(`/api/hot_topics/${topic.id}/analysis`, {
        angle: selectedAngle,
      });
      setAnalysis(data);
      if (data.recommended_frame) {
        setSelectedAngle(data.recommended_frame);
      }
    } catch (e: unknown) {
      setError(getErrorMessage(e, '深挖失败，当前轻分析仍可继续生成'));
    } finally {
      setDigging(false);
    }
  }

  async function handleQuickGenerate() {
    if (!topic || !selectedAngle.trim()) {
      setError('请选择一个写作角度');
      return;
    }

    setSubmitting('quick');
    setError('');
    try {
      const selected = await createCheckin();
      const draft = await api.postGeneration<{ content: string; platform: Platform; char_count: number }>('/api/quick_generate', {
        topic_id: topic.id,
        checkin_id: selected.checkin_id,
        hot_topic: topic.title,
        angle: selectedAngle.trim(),
        platform,
        opportunities: analysis?.opportunities ?? [],
        risks: analysis?.risks ?? [],
      });
      sessionStorage.setItem('current_draft', draft.content);
      router.push(`/preview?checkin_id=${selected.checkin_id}`);
    } catch (e: unknown) {
      setError(getErrorMessage(e, '生成草稿失败'));
      setSubmitting(null);
    }
  }

  async function handleDeepDiscuss() {
    if (!topic) return;
    setSubmitting('deep');
    setError('');
    try {
      const selected = await createCheckin();
      const query = new URLSearchParams({
        checkin_id: String(selected.checkin_id),
        topic: topic.title,
        angle: selectedAngle,
        platform,
      });
      router.push(`/discuss?${query.toString()}`);
    } catch (e: unknown) {
      setError(getErrorMessage(e, '进入深度讨论失败'));
      setSubmitting(null);
    }
  }

  if (loading) {
    return (
      <div className="sf-shell">
        <div className="mb-4 h-8 w-32 animate-pulse rounded bg-white/60" />
        <div className="space-y-3">
          <div className="h-28 animate-pulse rounded-2xl bg-white/60" />
          <div className="h-40 animate-pulse rounded-2xl bg-white/60" />
          <div className="h-24 animate-pulse rounded-2xl bg-white/60" />
        </div>
      </div>
    );
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
        <div>
          <p className="sf-eyebrow">热点创作</p>
          <h1 className="sf-display mt-1 text-2xl font-semibold text-[var(--ink)]">先定角度，再生成</h1>
        </div>
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

      {topic ? (
        <div className="sf-page-grid">
          <div className="sf-page-main">
            <section className="sf-card mb-4 p-5 md:p-6">
              <div className="mb-3 flex items-start justify-between gap-3">
                <div>
                  <span className="sf-eyebrow">已选热点</span>
                  <h2 className="mt-2 text-base font-semibold leading-relaxed text-[var(--ink)] md:text-xl">{topic.title}</h2>
                  <p className="mt-1 text-xs text-[var(--ink-muted)]">
                    {topic.source}
                    {topic.published_at ? ` · ${topic.published_at}` : ''}
                  </p>
                </div>
                {topic.url && (
                  <a
                    href={topic.url}
                    target="_blank"
                    rel="noreferrer"
                    className="sf-pill flex-shrink-0 hover:border-primary hover:text-primary-dark"
                  >
                    原文
                  </a>
                )}
              </div>
              {topic.summary && <p className="text-sm leading-7 text-[var(--ink-soft)] md:text-base">{topic.summary}</p>}
            </section>

            <section className="sf-card mb-4 p-5 md:p-6">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="sf-display text-2xl font-semibold text-[var(--ink)]">轻分析</h2>
                <button
                  onClick={handleDigDeeper}
                  disabled={digging}
                  className="sf-btn-secondary min-h-9 px-3 text-xs disabled:opacity-50"
                >
                  {digging ? '深挖中...' : analysis ? '重新深挖' : '深挖一下'}
                </button>
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                {topic.ai_angle && (
                  <div>
                    <p className="mb-1 text-xs text-[var(--ink-muted)]">推荐角度</p>
                    <p className="h-full rounded-2xl bg-primary/5 px-3 py-2 text-sm leading-7 text-primary-dark">
                      {topic.ai_angle}
                    </p>
                  </div>
                )}
                {topic.ai_counter_angle && (
                  <div>
                    <p className="mb-1 text-xs text-[var(--ink-muted)]">反向角度</p>
                    <p className="h-full rounded-2xl bg-[rgba(235,226,213,0.5)] px-3 py-2 text-sm leading-7 text-[var(--ink-soft)]">
                      {topic.ai_counter_angle}
                    </p>
                  </div>
                )}
                <div>
                  <p className="mb-1 text-xs text-[var(--ink-muted)]">可写立场</p>
                  <p className="h-full rounded-2xl bg-white/60 px-3 py-2 text-sm leading-7 text-[var(--ink-soft)]">
                    不复述新闻，直接写这个热点最值得讨论、最容易引发分歧的判断。
                  </p>
                </div>
              </div>
            </section>

            {analysis && (
              <section className="sf-card mb-4 p-5 md:p-6">
                <h2 className="sf-display mb-3 text-2xl font-semibold text-[var(--ink)]">深挖结果</h2>
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <p className="mb-2 text-xs text-[var(--ink-muted)]">机会</p>
                    <div className="space-y-2">
                      {analysis.opportunities.map((item) => (
                        <p key={item} className="rounded-2xl bg-primary/5 px-3 py-2 text-sm leading-7 text-primary-dark">
                          {item}
                        </p>
                      ))}
                    </div>
                  </div>
                  <div>
                    <p className="mb-2 text-xs text-[var(--ink-muted)]">风险</p>
                    <div className="space-y-2">
                      {analysis.risks.map((item) => (
                        <p key={item} className="rounded-2xl bg-[rgba(181,106,91,0.1)] px-3 py-2 text-sm leading-7 text-[var(--danger)]">
                          {item}
                        </p>
                      ))}
                    </div>
                  </div>
                </div>
              </section>
            )}
          </div>

          <div className="sf-page-side">
            <section className="sf-card mb-4 p-5">
            <h2 className="sf-display mb-3 text-2xl font-semibold text-[var(--ink)]">写作角度</h2>
            <div className="space-y-2">
              {angleOptions.map((angle) => (
                <button
                  key={angle}
                  onClick={() => setSelectedAngle(angle)}
                  className={`w-full rounded-2xl border px-3 py-2 text-left text-sm leading-7 ${
                    selectedAngle === angle
                      ? 'border-primary bg-primary/5 text-primary-dark'
                      : 'border-[var(--border)] bg-white/50 text-[var(--ink-soft)] hover:border-[var(--border-strong)]'
                  }`}
                >
                  {angle}
                </button>
              ))}
            </div>
            </section>

            <section className="sf-card mb-5 p-5">
            <h2 className="sf-display mb-3 text-2xl font-semibold text-[var(--ink)]">发布平台</h2>
            <div className="grid grid-cols-2 gap-2">
              {PLATFORM_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  onClick={() => handlePlatformChange(option.value)}
                  className={`rounded-2xl border px-3 py-2 text-left ${
                    platform === option.value
                      ? 'border-primary bg-primary/5'
                      : 'border-[var(--border)] bg-white/50 hover:border-[var(--border-strong)]'
                  }`}
                >
                  <p className={`text-sm font-medium ${platform === option.value ? 'text-primary-dark' : 'text-[var(--ink)]'}`}>
                    {option.label}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-[var(--ink-muted)]">{option.hint}</p>
                </button>
              ))}
            </div>
            </section>

            <div className="flex gap-3">
            <button
              onClick={handleDeepDiscuss}
              disabled={!!submitting}
              className="sf-btn-secondary flex-1"
            >
              {submitting === 'deep' ? '进入中...' : '深度讨论'}
            </button>
            <button
              onClick={handleQuickGenerate}
              disabled={!!submitting || !selectedAngle.trim()}
              className="sf-btn-primary flex-1"
            >
              {submitting === 'quick' ? '生成中...' : '生成草稿'}
            </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="sf-card px-4 py-8 text-center">
          <p className="mb-4 text-sm text-[var(--ink-soft)]">没有找到这个热点。</p>
          <Link
            href="/topics"
            className="sf-btn-primary"
          >
            返回选题
          </Link>
        </div>
      )}
    </div>
  );
}

export default function ComposePage() {
  return (
    <ProtectedRoute>
      <Suspense fallback={<div className="flex h-screen items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" /></div>}>
        <ComposeContent />
      </Suspense>
    </ProtectedRoute>
  );
}
