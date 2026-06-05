'use client';

import { useEffect, useRef, useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import ProtectedRoute from '@/components/ProtectedRoute';
import { api, getErrorMessage } from '@/lib/api';
import TemplateBeige from '@/components/post-templates/TemplateBeige';
import TemplateMagazine from '@/components/post-templates/TemplateMagazine';
import { renderPageToPng, downloadAsZip, downloadSinglePng } from '@/lib/composeImage';

interface PublishResult {
  message: string;
}

interface CheckinPayload {
  id: number;
  topic: string;
  content: string | null;
  status: string;
  content_approved: boolean;
  content_feedback?: string | null;
}

interface ComposeAssets {
  pages: string[];
  title: string;
  tags: string[];
}

type Step = 'preview' | 'quality_check' | 'quality_result' | 'composing' | 'compose_ready' | 'publishing';

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
  const [qualityPass, setQualityPass] = useState<boolean | null>(null);
  const [qualityIssues, setQualityIssues] = useState<string[]>([]);
  const [feedbackSent, setFeedbackSent] = useState(false);
  const [checkinStatus, setCheckinStatus] = useState('');

  const [template, setTemplate] = useState<'beige' | 'magazine'>('beige');
  const [composeAssets, setComposeAssets] = useState<ComposeAssets | null>(null);
  const [pngs, setPngs] = useState<string[]>([]);
  const [renderingImages, setRenderingImages] = useState(false);
  const [copiedTitle, setCopiedTitle] = useState(false);
  const [copiedTags, setCopiedTags] = useState(false);
  const templateRefs = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    const draft = sessionStorage.getItem('current_draft') ?? '';
    setContent(draft);
    if (!checkinId) return;

    api.get<CheckinPayload>(`/api/checkin/${checkinId}`)
      .then((data) => {
        setTopic(data.topic);
        setCheckinStatus(data.status);
        if (data.content) setContent(data.content);
        setFeedbackSent(data.content_feedback === 'down');
      })
      .catch(() => {});
  }, [checkinId]);

  // Re-render PNGs whenever assets or template changes
  useEffect(() => {
    if (!composeAssets || step !== 'compose_ready') return;

    let cancelled = false;

    async function renderAll() {
      setRenderingImages(true);
      setPngs([]);
      try {
        await document.fonts.ready;
        const results: string[] = [];
        for (let i = 0; i < composeAssets!.pages.length; i++) {
          if (cancelled) break;
          const ref = templateRefs.current[i];
          if (ref) {
            const png = await renderPageToPng(ref);
            results.push(png);
          }
        }
        if (!cancelled) setPngs(results);
      } finally {
        if (!cancelled) setRenderingImages(false);
      }
    }

    const timer = setTimeout(renderAll, 120);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [composeAssets, template, step]);

  async function handleCheckQuality() {
    const text = content.trim();
    if (!text) { setError('内容不能为空'); return; }
    setSubmitting(true);
    setError('');
    setStep('quality_check');
    try {
      const reviewEndpoint = checkinStatus === 'completed' ? '/api/review_content' : '/api/confirm_content';
      const review = await api.postGeneration<{
        content_approved: boolean;
        quality_issues: string[];
        fact_pass?: boolean;
        fact_issues?: string[];
        discussion_pass?: boolean;
        discussion_issues?: string[];
        topic: string;
      }>(reviewEndpoint, { checkin_id: checkinId, content: text });
      setTopic(review.topic);
      setQualityPass(review.content_approved);
      if (checkinStatus !== 'completed') setCheckinStatus('pending');
      setQualityIssues([
        ...(review.fact_issues ?? []),
        ...(review.discussion_issues ?? []),
        ...(review.quality_issues ?? []),
      ]);
      setStep('quality_result');
    } catch (e: unknown) {
      setError(getErrorMessage(e, '质量提示获取失败，请重试'));
      setStep('preview');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCompose(regenerate = false) {
    setSubmitting(true);
    setError('');
    setStep('composing');
    try {
      const assets = await api.postGeneration<ComposeAssets>('/api/compose_post_assets', {
        checkin_id: checkinId,
        template,
        regenerate,
      });
      setComposeAssets(assets);
      setCopiedTitle(false);
      setCopiedTags(false);
      setStep('compose_ready');
    } catch (e: unknown) {
      setError(getErrorMessage(e, '图文素材生成失败，请重试'));
      setStep('quality_result');
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
    } catch (e: unknown) {
      setError(getErrorMessage(e, '发布失败，请重试'));
      setStep('compose_ready');
      setSubmitting(false);
    }
  }

  async function handleFeedback() {
    if (feedbackSent || !checkinId) return;
    try {
      await api.post('/api/content_feedback', {
        checkin_id: checkinId,
        feedback: 'down',
        reason_tags: qualityIssues.length ? ['quality_issue'] : ['too_flat'],
      });
      setFeedbackSent(true);
    } catch { /* best-effort */ }
  }

  async function handleReviseFromIssues() {
    if (!checkinId || submitting) return;
    const text = content.trim();
    if (!text) { setError('内容不能为空'); setStep('preview'); return; }
    setSubmitting(true);
    setError('');
    try {
      const revised = await api.postGeneration<{
        content: string;
        char_count: number;
        fact_pass?: boolean;
        fact_issues?: string[];
        discussion_pass?: boolean;
        discussion_issues?: string[];
      }>('/api/revise_content', {
        checkin_id: checkinId,
        content: text,
        issues: qualityIssues,
        instruction: '根据发布提示改一版，保留原角度，但表达更有讨论性。',
      });
      setContent(revised.content);
      sessionStorage.setItem('current_draft', revised.content);
      setQualityPass(null);
      setQualityIssues([
        ...(revised.fact_issues ?? []),
        ...(revised.discussion_issues ?? []),
      ]);
      setStep('preview');
    } catch (e: unknown) {
      setError(getErrorMessage(e, '按提示改写失败，请稍后重试'));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCopyTitle() {
    if (!composeAssets) return;
    try {
      await navigator.clipboard.writeText(composeAssets.title);
      setCopiedTitle(true);
      setTimeout(() => setCopiedTitle(false), 2000);
    } catch { /* user can select manually */ }
  }

  async function handleCopyTags() {
    if (!composeAssets) return;
    const tagText = composeAssets.tags.map(t => `#${t}`).join(' ');
    try {
      await navigator.clipboard.writeText(tagText);
      setCopiedTags(true);
      setTimeout(() => setCopiedTags(false), 2000);
    } catch { /* best-effort */ }
  }

  if (result) {
    return (
      <div className="sf-shell md:max-w-4xl">
        <div className="sf-card mx-auto max-w-2xl p-8 text-center">
          <p className="sf-eyebrow">发布完成</p>
          <h1 className="sf-display mt-4 text-[40px] font-bold leading-tight text-[var(--ink)]">这篇已经发出去了</h1>
          <p className="mx-auto mt-4 max-w-md text-sm leading-7 text-[var(--ink-soft)]">
            内容已经进入历史稿件。之后可以回看，也可以从新的热点继续写下一篇。
          </p>
          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <Link href="/history?tab=completed" className="sf-btn-secondary flex-1">查看历史稿件</Link>
            <button onClick={() => router.push('/')} className="sf-btn-primary flex-1">返回首页</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="sf-shell md:max-w-4xl xl:max-w-4xl">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => router.back()} className="text-gray-500 hover:text-gray-700">←</button>
        <div>
          <h1 className="text-xl font-bold text-gray-900">预览 & 发布</h1>
          {topic && (
            <p className="mt-1 text-xs text-gray-400">
              #{topic}{checkinStatus === 'completed' ? ' · 已发布' : ''}
            </p>
          )}
        </div>
      </div>

      {/* Text preview + quality check */}
      {(step === 'preview' || step === 'quality_check') && (
        <>
          <div className="mb-4">
            <div className="flex justify-between items-center mb-2">
              <label className="text-sm font-medium text-gray-700">文章内容</label>
              <span className="text-xs text-gray-400">
                {content.length} 字{content.length < 140 && ' · 建议 140-300 字'}
              </span>
            </div>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={12}
              disabled={step === 'quality_check'}
              className="min-h-80 w-full rounded-xl border border-gray-300 px-4 py-3 text-sm leading-relaxed focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-60 md:text-base"
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

      {/* Quality result */}
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
                disabled={submitting}
                className="flex-1 rounded-xl border border-gray-300 py-2 text-sm text-gray-700 hover:bg-white disabled:opacity-50"
              >
                返回修改
              </button>
              {checkinStatus !== 'completed' && (
                <button
                  onClick={handleReviseFromIssues}
                  disabled={submitting}
                  className="flex-1 rounded-xl bg-primary py-2 text-sm font-medium text-white hover:bg-primary-dark disabled:opacity-50"
                >
                  {submitting ? '改写中...' : '按提示改一版'}
                </button>
              )}
              <button
                onClick={handleFeedback}
                disabled={feedbackSent || submitting}
                className="flex-1 rounded-xl border border-amber-300 py-2 text-sm text-amber-700 disabled:opacity-60"
              >
                {feedbackSent ? '已记录这版一般' : '这版一般'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Composing loading */}
      {step === 'composing' && (
        <div className="mb-4 rounded-2xl bg-white px-4 py-5 text-center shadow-sm">
          <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          <p className="text-sm text-gray-600">AI 正在生成图文素材...</p>
        </div>
      )}

      {/* Compose ready — gallery + title + tags */}
      {step === 'compose_ready' && composeAssets && (
        <div className="mb-4 space-y-4">
          {/* Template selector + re-roll */}
          <div className="flex items-center justify-between">
            <div className="flex gap-2">
              <button
                onClick={() => setTemplate('beige')}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  template === 'beige'
                    ? 'bg-primary text-white'
                    : 'border border-gray-300 text-gray-600 hover:bg-gray-50'
                }`}
              >
                衬线研究卡
              </button>
              <button
                onClick={() => setTemplate('magazine')}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  template === 'magazine'
                    ? 'bg-primary text-white'
                    : 'border border-gray-300 text-gray-600 hover:bg-gray-50'
                }`}
              >
                绿调索引卡
              </button>
            </div>
            <button
              onClick={() => handleCompose(true)}
              disabled={submitting || renderingImages}
              className="text-xs text-primary hover:underline disabled:opacity-50"
            >
              换一版
            </button>
          </div>

          {/* Off-screen template DOM elements for html2canvas capture */}
          <div style={{ position: 'fixed', left: '-9999px', top: '-9999px', zIndex: -1 }}>
            {composeAssets.pages.map((pageText, i) => (
              <div
                key={`${template}-${i}-${composeAssets.pages.length}`}
                ref={(el) => { templateRefs.current[i] = el; }}
              >
                {template === 'beige' ? (
                  <TemplateBeige
                    pageText={pageText}
                    pageIndex={i}
                    totalPages={composeAssets.pages.length}
                  />
                ) : (
                  <TemplateMagazine
                    pageText={pageText}
                    pageIndex={i}
                    totalPages={composeAssets.pages.length}
                  />
                )}
              </div>
            ))}
          </div>

          {/* Image gallery */}
          {renderingImages ? (
            <div className="rounded-2xl bg-white px-4 py-5 text-center shadow-sm">
              <div className="mx-auto mb-3 h-6 w-6 animate-spin rounded-full border-4 border-primary border-t-transparent" />
              <p className="text-sm text-gray-500">渲染图片中...</p>
            </div>
          ) : (
            <div>
              <div className="flex gap-3 overflow-x-auto pb-2">
                {pngs.map((png, i) => (
                  <div key={i} className="flex-shrink-0">
                    <img
                      src={png}
                      alt={`第 ${i + 1} 张`}
                      className="rounded-xl shadow-md"
                      style={{ width: '75vw', maxWidth: 300, aspectRatio: '3/4', objectFit: 'cover' }}
                    />
                    <button
                      onClick={() => downloadSinglePng(png, `顺发-${topic}-${i + 1}`)}
                      className="mt-2 w-full rounded-lg border border-gray-300 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
                    >
                      保存第 {i + 1} 张
                    </button>
                  </div>
                ))}
              </div>
              {pngs.length > 1 && (
                <button
                  onClick={() => downloadAsZip(pngs, `顺发-${topic}`)}
                  className="mt-2 w-full rounded-xl border border-gray-300 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  下载全部 ZIP（{pngs.length} 张）
                </button>
              )}
            </div>
          )}

          {/* Title card */}
          <div className="rounded-2xl bg-white px-4 py-4 shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">小红书标题</span>
              <button onClick={handleCopyTitle} className="text-xs text-primary hover:underline">
                {copiedTitle ? '已复制 ✓' : '复制'}
              </button>
            </div>
            <p className="text-sm text-gray-900 leading-relaxed">{composeAssets.title}</p>
          </div>

          {/* Tags card */}
          <div className="rounded-2xl bg-white px-4 py-4 shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">标签</span>
              <button onClick={handleCopyTags} className="text-xs text-primary hover:underline">
                {copiedTags ? '已复制 ✓' : '复制全部'}
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {composeAssets.tags.map((tag) => (
                <span
                  key={tag}
                  className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-700"
                >
                  #{tag}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Publishing loading */}
      {step === 'publishing' && (
        <div className="mb-4 rounded-2xl bg-white px-4 py-5 text-center shadow-sm">
          <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          <p className="text-sm text-gray-600">记录打卡中...</p>
        </div>
      )}

      {error && (
        <div className="mb-4 px-4 py-2 bg-red-50 text-red-600 rounded-xl text-sm">{error}</div>
      )}

      {/* CTA buttons */}
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
            {submitting ? '评估中...' : checkinStatus === 'completed' ? '查看内容提示' : '查看发布提示'}
          </button>
        </div>
      )}

      {step === 'quality_result' && (
        <div className="flex gap-3">
          {(qualityPass || checkinStatus === 'completed') && (
            <button
              onClick={() => setStep('preview')}
              className="flex-1 py-3 border border-gray-300 rounded-xl text-sm text-gray-700 hover:bg-gray-50"
            >
              返回修改
            </button>
          )}
          {checkinStatus !== 'completed' ? (
            <button
              onClick={() => handleCompose(false)}
              disabled={submitting}
              className="flex-1 py-3 bg-primary text-white rounded-xl text-sm font-medium disabled:opacity-50 hover:bg-primary-dark transition-colors"
            >
              {submitting ? '生成中...' : '生成图文素材'}
            </button>
          ) : (
            <Link
              href="/history?tab=completed"
              className="flex-1 rounded-xl bg-primary py-3 text-center text-sm font-medium text-white transition-colors hover:bg-primary-dark"
            >
              返回历史
            </Link>
          )}
        </div>
      )}

      {step === 'compose_ready' && checkinStatus !== 'completed' && (
        <div className="flex gap-3">
          <button
            onClick={() => setStep('quality_result')}
            className="flex-1 py-3 border border-gray-300 rounded-xl text-sm text-gray-700 hover:bg-gray-50"
          >
            返回修改
          </button>
          <button
            onClick={handlePublish}
            disabled={submitting || renderingImages}
            className="flex-1 py-3 bg-primary text-white rounded-xl text-sm font-medium disabled:opacity-50 hover:bg-primary-dark transition-colors"
          >
            {submitting ? '记录中...' : '我已发到小红书，确认打卡'}
          </button>
        </div>
      )}
    </div>
  );
}

export default function PreviewPage() {
  return (
    <ProtectedRoute>
      <Suspense fallback={
        <div className="flex items-center justify-center h-screen">
          <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      }>
        <PreviewContent />
      </Suspense>
    </ProtectedRoute>
  );
}
