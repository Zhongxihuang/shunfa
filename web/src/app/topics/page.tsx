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

function TopicsContent() {
  const router = useRouter();
  const [topics, setTopics] = useState<TopicItem[]>([]);
  const [refreshCount, setRefreshCount] = useState(0);
  const [maxRefreshes, setMaxRefreshes] = useState(3);
  const [loading, setLoading] = useState(false);
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);
  const [customTopic, setCustomTopic] = useState('');
  const [showCustom, setShowCustom] = useState(false);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadTopics();
  }, []);

  async function loadTopics() {
    setLoading(true);
    setError('');
    try {
      const data = await api.post<{ topics: TopicItem[]; refresh_count: number; max_refreshes: number }>('/api/daily_topics');
      setTopics(data.topics);
      setRefreshCount(data.refresh_count);
      setMaxRefreshes(data.max_refreshes);
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
    <div className="max-w-md mx-auto px-4 pt-6 pb-8">
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => router.back()} className="text-gray-500 hover:text-gray-700">
          ←
        </button>
        <h1 className="text-xl font-bold text-gray-900">选择今日话题</h1>
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 text-red-600 rounded-xl text-sm">
          <p>{error}</p>
          {error.includes('API Key') && (
            <Link href="/settings" className="mt-1 inline-block text-primary underline font-medium">
              前往设置页面配置 →
            </Link>
          )}
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 bg-gray-100 rounded-xl animate-pulse" />
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
        className="w-full py-2.5 border border-gray-300 rounded-xl text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-40 mb-4"
      >
        换一批（剩余 {maxRefreshes - refreshCount} 次）
      </button>

      <div className="flex items-center gap-3 mb-4">
        <div className="flex-1 border-t border-gray-200" />
        <span className="text-sm text-gray-400">或者</span>
        <div className="flex-1 border-t border-gray-200" />
      </div>

      <button
        onClick={() => setShowCustom(!showCustom)}
        className="w-full py-2.5 border border-dashed border-gray-300 rounded-xl text-sm text-gray-500 hover:bg-gray-50 mb-3"
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
              className="w-full px-4 py-3 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">
              {customTopic.length}/50
            </span>
          </div>
        </div>
      )}

      <button
        onClick={handleConfirm}
        disabled={submitting || (!selectedTopic && !customTopic.trim())}
        className="w-full py-3 bg-primary text-white rounded-xl font-medium disabled:opacity-50 hover:bg-primary-dark transition-colors"
      >
        {submitting ? '跳转中...' : '开始写作 →'}
      </button>
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
