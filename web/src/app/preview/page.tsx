'use client';

import { useEffect, useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import AchievementBadge from '@/components/AchievementBadge';
import { api } from '@/lib/api';

interface PublishResult {
  streak: number;
  points_earned: number;
  total_points: number;
  level: number;
  diamonds: number;
  message: string;
  newly_unlocked: Array<{ type: string; name: string; desc: string }>;
}

interface CheckinPayload {
  id: number;
  topic: string;
  content: string | null;
  status: string;
  content_approved: boolean;
  content_feedback?: string | null;
}

type Step = 'preview' | 'quality_check' | 'quality_result' | 'publishing';

function PreviewContent() {
  const router = useRouter();
  const params = useSearchParams();
  const checkinId = parseInt(params.get('checkin_id') ?? '0');

  const [topic, setTopic] = useState('');
  const [content, setContent] = useState('');
  const [step, setStep] = useState<Step>('preview');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<PublishResult | null>(null);
  const [showAchievements, setShowAchievements] = useState(false);
  const [qualityPass, setQualityPass] = useState<boolean | null>(null);
  const [qualityIssues, setQualityIssues] = useState<string[]>([]);
  const [feedbackSent, setFeedbackSent] = useState(false);

  useEffect(() => {
    const draft = sessionStorage.getItem('current_draft') ?? '';
    setContent(draft);
    if (!checkinId) return;

    api.get<CheckinPayload>(`/api/checkin/${checkinId}`)
      .then((data) => {
        setTopic(data.topic);
        if (data.content) {
          setContent(data.content);
        }
        setFeedbackSent(data.content_feedback === 'down');
      })
      .catch(() => {});
  }, [checkinId]);

  async function handleCheckQuality() {
    const text = content.trim();
    if (!text) {
      setError('内容不能为空');
      return;
    }

    setSubmitting(true);
    setError('');
    setStep('quality_check');

    try {
      const review = await api.post<{
        content_approved: boolean;
        quality_issues: string[];
        topic: string;
      }>('/api/confirm_content', { checkin_id: checkinId, content: text });
      setTopic(review.topic);
      setQualityPass(review.content_approved);
      setQualityIssues(review.quality_issues ?? []);
      setStep('quality_result');
    } catch (e: unknown) {
      const err = e as { data?: { detail?: string } };
      setError(err?.data?.detail ?? '质量提示获取失败，请重试');
      setStep('preview');
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePublish() {
    setSubmitting(true);
    setError('');
    setStep('publishing');

    try {
      const data = await api.post<PublishResult>('/api/confirm_publish', { checkin_id: checkinId });
      setResult(data);
      if (data.newly_unlocked?.length > 0) {
        setShowAchievements(true);
      }
    } catch (e: unknown) {
      const err = e as { data?: { detail?: string } };
      setError(err?.data?.detail ?? '发布失败，请重试');
      setStep('quality_result');
      setSubmitting(false);
    }
  }

  async function handleFeedback() {
    if (feedbackSent || !checkinId) return;
    try {
      await api.post('/api/content_feedback', { checkin_id: checkinId, feedback: 'down' });
      setFeedbackSent(true);
    } catch {
      // Best-effort signal only.
    }
  }

  if (result) {
    return (
      <div className="max-w-md mx-auto px-4 pt-8 pb-8">
        <div className="text-center mb-8">
          <div className="text-5xl mb-4">🎉</div>
          <h1 className="text-2xl font-bold text-gray-900 mb-2">发布成功！</h1>
          <p className="text-gray-600">{result.message}</p>
        </div>

        <div className="bg-white rounded-2xl p-5 shadow-sm mb-4">
          <div className="grid grid-cols-2 gap-4 text-center">
            <div>
              <div className="text-2xl font-bold text-primary">+{result.points_earned}</div>
              <div className="text-xs text-gray-500">本次获得积分</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-gray-800">{result.streak}</div>
              <div className="text-xs text-gray-500">连续天数 🔥</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-gray-800">{result.total_points}</div>
              <div className="text-xs text-gray-500">总积分</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-gray-800">{result.diamonds}</div>
              <div className="text-xs text-gray-500">💎 钻石</div>
            </div>
          </div>
        </div>

        {showAchievements && result.newly_unlocked.length > 0 && (
          <div className="bg-white rounded-2xl p-5 shadow-sm mb-4">
            <h2 className="font-semibold text-gray-800 mb-3">🏆 新成就解锁！</h2>
            <div className="grid grid-cols-3 gap-3">
              {result.newly_unlocked.map((a) => (
                <AchievementBadge key={a.type} type={a.type} name={a.name} unlocked />
              ))}
            </div>
          </div>
        )}

        <button
          onClick={() => router.push('/')}
          className="w-full py-3 bg-primary text-white rounded-xl font-medium hover:bg-primary-dark transition-colors"
        >
          返回首页
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto px-4 pt-6 pb-8">
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => router.back()} className="text-gray-500 hover:text-gray-700">
          ←
        </button>
        <div>
          <h1 className="text-xl font-bold text-gray-900">预览 & 发布</h1>
          {topic && <p className="mt-1 text-xs text-gray-400">#{topic}</p>}
        </div>
      </div>

      {(step === 'preview' || step === 'quality_check') && (
        <>
          <div className="mb-4">
            <div className="flex justify-between items-center mb-2">
              <label className="text-sm font-medium text-gray-700">文章内容</label>
              <span className="text-xs text-gray-400">{content.length} 字{content.length < 140 && ' · 建议 140-300 字'}</span>
            </div>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={12}
              disabled={step === 'quality_check'}
              className="w-full px-4 py-3 border border-gray-300 rounded-xl text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary disabled:opacity-60"
            />
          </div>

          {step === 'quality_check' && (
            <div className="mb-4 rounded-2xl bg-white px-4 py-5 text-center shadow-sm">
              <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
              <p className="text-sm text-gray-600">AI 正在生成质量提示...</p>
            </div>
          )}
        </>
      )}

      {step === 'quality_result' && (
        <div className={`mb-4 rounded-2xl border px-4 py-4 ${qualityPass ? 'border-emerald-200 bg-emerald-50' : 'border-amber-200 bg-amber-50'}`}>
          <div className="mb-3 flex items-center gap-2">
            <span>{qualityPass ? '✅' : '💡'}</span>
            <h2 className="text-sm font-semibold text-gray-900">
              {qualityPass ? '内容质量良好' : '内容可以更好'}
            </h2>
          </div>
          <p className="mb-3 text-xs text-gray-500">以下只是提示，不影响发布。</p>
          {qualityIssues.length > 0 && (
            <div className="space-y-1">
              {qualityIssues.map((issue) => (
                <p key={issue} className="text-sm text-gray-700">- {issue}</p>
              ))}
            </div>
          )}
          {!qualityPass && (
            <div className="mt-4 flex gap-2">
              <button
                onClick={() => setStep('preview')}
                className="flex-1 rounded-xl border border-gray-300 py-2 text-sm text-gray-700 hover:bg-white"
              >
                返回修改
              </button>
              <button
                onClick={handleFeedback}
                disabled={feedbackSent}
                className="flex-1 rounded-xl border border-amber-300 py-2 text-sm text-amber-700 disabled:opacity-60"
              >
                {feedbackSent ? '已记录这版一般' : '这版一般'}
              </button>
            </div>
          )}
        </div>
      )}

      {step === 'publishing' && (
        <div className="mb-4 rounded-2xl bg-white px-4 py-5 text-center shadow-sm">
          <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          <p className="text-sm text-gray-600">发布中...</p>
        </div>
      )}

      {error && (
        <div className="mb-4 px-4 py-2 bg-red-50 text-red-600 rounded-xl text-sm">{error}</div>
      )}

      {step === 'preview' && (
        <div className="flex gap-3">
          <button
            onClick={() => router.back()}
            className="flex-1 py-3 border border-gray-300 rounded-xl text-sm text-gray-700 hover:bg-gray-50"
          >
            返回修改
          </button>
          <button
            onClick={handleCheckQuality}
            disabled={submitting || !content.trim()}
            className="flex-1 py-3 bg-primary text-white rounded-xl text-sm font-medium disabled:opacity-50 hover:bg-primary-dark transition-colors"
          >
            {submitting ? '评估中...' : '查看发布提示'}
          </button>
        </div>
      )}

      {step === 'quality_result' && (
        <div className="flex gap-3">
          {qualityPass && (
            <button
              onClick={() => setStep('preview')}
              className="flex-1 py-3 border border-gray-300 rounded-xl text-sm text-gray-700 hover:bg-gray-50"
            >
              返回修改
            </button>
          )}
          <button
            onClick={handlePublish}
            disabled={submitting}
            className="flex-1 py-3 bg-primary text-white rounded-xl text-sm font-medium disabled:opacity-50 hover:bg-primary-dark transition-colors"
          >
            {submitting ? '发布中...' : qualityPass ? '确认发布' : '仍然发布'}
          </button>
        </div>
      )}
    </div>
  );
}

export default function PreviewPage() {
  return (
    <ProtectedRoute>
      <Suspense fallback={<div className="flex items-center justify-center h-screen"><div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" /></div>}>
        <PreviewContent />
      </Suspense>
    </ProtectedRoute>
  );
}
