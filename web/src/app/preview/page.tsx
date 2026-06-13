'use client';

import { useCallback, useEffect, useRef, useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import ProtectedRoute from '@/components/ProtectedRoute';
import Spinner from '@/components/Spinner';
import { api, getErrorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
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

interface FormattedPost {
  checkin_id: number;
  platform: string;
  requested_platform: string;
  title: string;
  body: string;
  tags: string[];
  char_count: number;
  truncated: boolean;
  truncated_marker: string;
  text: string;
}

type PlatformId =
  | 'xiaohongshu'
  | 'moments'
  | 'wechat_official'
  | 'twitter'
  | 'weibo'
  | 'generic';

interface PlatformOption {
  id: PlatformId;
  label: string;
  hint: string;
}

const PLATFORMS: PlatformOption[] = [
  { id: 'xiaohongshu', label: '小红书', hint: '≤1000 字 · 末尾加 #tag' },
  { id: 'moments', label: '朋友圈', hint: '≤150 字 · 1 个 #tag' },
  { id: 'wechat_official', label: '公众号', hint: '长文 · 无 #tag' },
  { id: 'weibo', label: '微博', hint: '≤140 字 · #tag# 包围' },
  { id: 'twitter', label: 'Twitter', hint: '≤280 字' },
  { id: 'generic', label: '通用', hint: '未指定平台' },
];

type Step = 'preview' | 'quality_check' | 'quality_result' | 'composing' | 'compose_ready' | 'publishing';

function PreviewContent() {
  const router = useRouter();
  const params = useSearchParams();
  const checkinId = parseInt(params.get('checkin_id') ?? '0');
  const { user, refreshUser } = useAuth();

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
  const [checkinLoading, setCheckinLoading] = useState(true);
  const [checkinLoadError, setCheckinLoadError] = useState('');

  const [template, setTemplate] = useState<'beige' | 'magazine'>('beige');
  const [composeAssets, setComposeAssets] = useState<ComposeAssets | null>(null);
  const [pngs, setPngs] = useState<string[]>([]);
  const [renderingImages, setRenderingImages] = useState(false);
  const [copiedTitle, setCopiedTitle] = useState(false);
  const [copiedTags, setCopiedTags] = useState(false);
  const templateRefs = useRef<(HTMLDivElement | null)[]>([]);

  // W1.4: 多平台格式 + 导出
  const [selectedPlatform, setSelectedPlatform] = useState<PlatformId>('xiaohongshu');
  const [formatted, setFormatted] = useState<FormattedPost | null>(null);
  const [formatting, setFormatting] = useState(false);
  const [formatError, setFormatError] = useState('');
  const [copiedFormatted, setCopiedFormatted] = useState(false);
  const [downloadingFormat, setDownloadingFormat] = useState<'md' | 'txt' | null>(null);

  const loadCheckin = useCallback(() => {
    const draft = sessionStorage.getItem('current_draft') ?? '';
    setContent(draft);
    setCheckinLoadError('');
    if (!checkinId) {
      setCheckinLoading(false);
      setCheckinLoadError('缺少稿件 ID，请从草稿箱或历史记录重新进入。');
      return;
    }

    setCheckinLoading(true);
    api.get<CheckinPayload>(`/api/checkin/${checkinId}`)
      .then((data) => {
        setTopic(data.topic);
        setCheckinStatus(data.status);
        if (data.content) setContent(data.content);
        setFeedbackSent(data.content_feedback === 'down');
        setCheckinLoadError('');
      })
      .catch((e: unknown) => {
        setCheckinLoadError(getErrorMessage(e, '稿件加载失败，请重试。'));
      })
      .finally(() => setCheckinLoading(false));
  }, [checkinId]);

  useEffect(() => loadCheckin(), [loadCheckin]);

  // Re-render PNGs whenever assets or template changes. `step` is in deps only
  // as a *gate* — if PNGs already match the current assets+template, do not
  // re-render (publish-failure rolls `step` back to 'compose_ready' without
  // touching the image, and we don't want to re-run html2canvas for that).
  useEffect(() => {
    if (!composeAssets || step !== 'compose_ready') return;

    // Skip when we already have a full set of rendered PNGs for this
    // assets+template combo. Bumping the template still re-renders because
    // `template` is in the deps array.
    if (pngs.length === composeAssets.pages.length) return;

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
    // `pngs` is intentionally NOT a dep — it's only read for the skip check,
    // and including it would re-trigger render on every setPngs() tick.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [composeAssets, template, step]);

  async function handleCheckQuality() {
    const text = content.trim();
    if (!text) { setError('内容不能为空'); return; }
    if (checkinLoadError || checkinLoading) {
      setError('稿件信息尚未成功加载，不能继续发布。');
      return;
    }
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
      await refreshUser();
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

  // W2.x bridge: hand the current draft to /image-cards via localStorage
  // (URL params cap at ~2KB; a 20k-char paste would not survive the navigation).
  function handleBridgeToImageCards() {
    if (!content.trim()) return;
    try {
      const payload = {
        raw_text: content,
        cover_title: composeAssets?.title?.trim() || '',
        ts: Date.now(),
      };
      localStorage.setItem('shunfa:image-cards-prefill', JSON.stringify(payload));
    } catch {
      // localStorage might be full / disabled — degrade silently and let the
      // user paste manually on the other side.
    }
    router.push('/image-cards');
  }

  // W1.4: 拉取目标平台格式化的文本. 触发后,用户点"复制"就是第 2 步.
  async function handleFormatForPlatform(platform: PlatformId) {
    if (!checkinId || formatting) return;
    setSelectedPlatform(platform);
    setFormatting(true);
    setFormatError('');
    setCopiedFormatted(false);
    try {
      const resp = await api.post<FormattedPost>('/api/preview/format', {
        checkin_id: checkinId,
        platform,
      });
      setFormatted(resp);
    } catch (e: unknown) {
      setFormatError(getErrorMessage(e, '格式化失败,请重试'));
      setFormatted(null);
    } finally {
      setFormatting(false);
    }
  }

  async function handleCopyFormatted() {
    if (!formatted) return;
    try {
      await navigator.clipboard.writeText(formatted.text);
      setCopiedFormatted(true);
      setTimeout(() => setCopiedFormatted(false), 2000);
      // 埋点: 真实"复制"动作
      api.post('/api/event/track', {
        event: `copy_to_${formatted.platform}`,
        props: { checkin_id: checkinId, char_count: formatted.char_count },
      }).catch(() => { /* best-effort */ });
    } catch { /* user can select manually */ }
  }

  async function handleDownload(format: 'md' | 'txt') {
    if (!checkinId || downloadingFormat) return;
    setDownloadingFormat(format);
    try {
      const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
      const url = `/api/preview/export?checkin_id=${checkinId}&format=${format}`;
      const resp = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const blob = await resp.blob();
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objectUrl;
      a.download = `shunfa-checkin-${checkinId}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objectUrl);
      api.post('/api/event/track', {
        event: `export_${format}`,
        props: { checkin_id: checkinId },
      }).catch(() => { /* best-effort */ });
    } catch (e: unknown) {
      setFormatError(getErrorMessage(e, '下载失败,请重试'));
    } finally {
      setDownloadingFormat(null);
    }
  }

  if (result) {
    return (
      <div className="sf-shell md:max-w-4xl">
        <div className="sf-card sf-rise mx-auto max-w-2xl p-8 text-center">
          <p className="sf-eyebrow">发布完成</p>
          <h1 className="sf-display mt-4 text-[40px] font-bold leading-tight text-[var(--ink)]">这篇已经发出去了</h1>
          {user && (
            <div className="mt-5 flex flex-wrap justify-center gap-3">
              <span className="sf-stat sf-stat-ember px-4 py-2 text-base font-semibold">
                🔥 已连更 {user.streak} 天！
              </span>
              <span className="sf-stat sf-stat-gold px-4 py-2 text-base font-semibold">
                ⭐ {user.points} 积分
              </span>
            </div>
          )}
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
      <div className="sf-rise mb-6 flex items-center gap-3">
        <button
          onClick={() => router.back()}
          aria-label="返回上一页"
          className="sf-btn-secondary h-10 min-h-10 w-10 px-0"
        >
          ←
        </button>
        <div>
          <p className="sf-eyebrow">预览 & 发布</p>
          <h1 className="sf-display mt-1 truncate text-2xl font-semibold text-[var(--ink)]">
            {topic || '最后看一眼，发出去'}
          </h1>
          {topic && checkinStatus === 'completed' && (
            <p className="mt-1 text-xs text-[var(--ink-muted)]">已发布</p>
          )}
        </div>
      </div>

      {/* Text preview + quality check */}
      {checkinLoadError && (
        <div className="sf-note-card mb-4 px-4 py-4">
          <p className="text-sm font-semibold text-[var(--ink)]">稿件加载失败</p>
          <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">{checkinLoadError}</p>
          <div className="mt-4 flex gap-3">
            <button onClick={loadCheckin} className="sf-btn-secondary min-h-10 flex-1 px-4">重新加载</button>
            <Link href="/drafts" className="sf-btn-primary min-h-10 flex-1 px-4">返回草稿箱</Link>
          </div>
        </div>
      )}

      {(step === 'preview' || step === 'quality_check') && (
        <>
          <div className="sf-rise sf-rise-1 mb-4">
            <div className="mb-2 flex items-center justify-between">
              <label className="text-sm font-medium text-[var(--ink-soft)]">文章内容</label>
              <span className="text-xs text-[var(--ink-muted)]">
                {content.length} 字{content.length < 140 && ' · 建议 140-300 字'}
              </span>
            </div>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={12}
              disabled={step === 'quality_check'}
              className="sf-textarea min-h-80 md:text-base"
            />
          </div>
          {step === 'quality_check' && (
            <div className="sf-card sf-fade mb-4 px-4 py-5 text-center">
              <Spinner className="mx-auto mb-3" />
              <p className="text-sm text-[var(--ink-soft)]">AI 正在审稿，通常需要 20-40 秒...</p>
            </div>
          )}
        </>
      )}

      {/* Quality result */}
      {step === 'quality_result' && (
        <div className={`sf-fade mb-4 rounded-2xl border px-5 py-4 ${
          qualityPass
            ? 'border-[rgba(111,135,115,0.25)] bg-[var(--accent-soft)]'
            : 'border-[rgba(170,151,123,0.25)] bg-[var(--highlight)]'
        }`}>
          <div className="mb-3 flex items-center gap-2">
            <span>{qualityPass ? '✅' : '💡'}</span>
            <h2 className="text-sm font-semibold text-[var(--ink)]">
              {qualityPass ? '内容质量良好' : '内容可以更好'}
            </h2>
          </div>
          <p className="mb-3 text-xs text-[var(--ink-muted)]">以下只是提示，不影响发布。</p>
          {qualityIssues.length > 0 && (
            <div className="space-y-1">
              {qualityIssues.map((issue) => (
                <p key={issue} className="text-sm leading-6 text-[var(--ink-soft)]">- {issue}</p>
              ))}
            </div>
          )}
          {!qualityPass && (
            <div className="mt-4 flex gap-2">
              <button
                onClick={() => setStep('preview')}
                disabled={submitting}
                className="sf-btn-secondary min-h-10 flex-1 px-3 text-xs"
              >
                返回修改
              </button>
              {checkinStatus !== 'completed' && (
                <button
                  onClick={handleReviseFromIssues}
                  disabled={submitting}
                  className="sf-btn-primary min-h-10 flex-1 px-3 text-xs"
                >
                  {submitting ? '改写中...' : '按提示改一版'}
                </button>
              )}
              <button
                onClick={handleFeedback}
                disabled={feedbackSent || submitting}
                className="min-h-10 flex-1 rounded-full border border-[rgba(170,151,123,0.4)] px-3 text-xs text-[var(--ink-soft)] transition hover:bg-white/50 disabled:opacity-60"
              >
                {feedbackSent ? '已记录这版一般' : '这版一般'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Composing loading */}
      {step === 'composing' && (
        <div className="sf-card sf-fade mb-4 px-4 py-5 text-center">
          <Spinner className="mx-auto mb-3" />
          <p className="text-sm text-[var(--ink-soft)]">AI 正在生成图文素材...</p>
        </div>
      )}

      {/* Compose ready — gallery + title + tags */}
      {step === 'compose_ready' && composeAssets && (
        <div className="mb-4 space-y-4">
          {/* Template selector + re-roll */}
          <div className="flex items-center justify-between">
            <div className="flex gap-2">
              {([['beige', '衬线研究卡'], ['magazine', '绿调索引卡']] as const).map(([id, label]) => (
                <button
                  key={id}
                  onClick={() => setTemplate(id)}
                  className={`rounded-full px-3.5 py-1.5 text-xs font-medium transition-colors ${
                    template === id
                      ? 'bg-[var(--ink)] text-white'
                      : 'border border-[var(--border-strong)] bg-white/60 text-[var(--ink-soft)] hover:bg-white'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <button
              onClick={() => handleCompose(true)}
              disabled={submitting || renderingImages}
              className="text-xs font-medium text-primary-dark hover:underline disabled:opacity-50"
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
            <div className="sf-card px-4 py-5 text-center">
              <Spinner size="sm" className="mx-auto mb-3" />
              <p className="text-sm text-[var(--ink-muted)]">渲染图片中...</p>
            </div>
          ) : (
            <div>
              <div className="flex gap-3 overflow-x-auto pb-2">
                {pngs.map((png, i) => (
                  <div key={i} className="flex-shrink-0">
                    {/* eslint-disable-next-line @next/next/no-img-element -- PNGs are client-rendered data URLs from html2canvas. */}
                    <img
                      src={png}
                      alt={`第 ${i + 1} 张`}
                      className="rounded-xl shadow-md"
                      style={{ width: '75vw', maxWidth: 300, aspectRatio: '3/4', objectFit: 'cover' }}
                    />
                    <button
                      onClick={() => downloadSinglePng(png, `顺发-${topic}-${i + 1}`)}
                      className="mt-2 w-full rounded-lg border border-[var(--border-strong)] bg-white/60 py-1.5 text-xs text-[var(--ink-soft)] transition hover:bg-white"
                    >
                      保存第 {i + 1} 张
                    </button>
                  </div>
                ))}
              </div>
              {pngs.length > 1 && (
                <button
                  onClick={() => downloadAsZip(pngs, `顺发-${topic}`)}
                  className="sf-btn-secondary mt-2 min-h-11 w-full"
                >
                  下载全部 ZIP（{pngs.length} 张）
                </button>
              )}
            </div>
          )}

          {/* Title card */}
          <div className="sf-card px-5 py-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="sf-eyebrow">小红书标题</span>
              <button onClick={handleCopyTitle} className="text-xs font-medium text-primary-dark hover:underline">
                {copiedTitle ? '已复制 ✓' : '复制'}
              </button>
            </div>
            <p className="text-sm leading-relaxed text-[var(--ink)]">{composeAssets.title}</p>
          </div>

          {/* Tags card */}
          <div className="sf-card px-5 py-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="sf-eyebrow">标签</span>
              <button onClick={handleCopyTags} className="text-xs font-medium text-primary-dark hover:underline">
                {copiedTags ? '已复制 ✓' : '复制全部'}
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {composeAssets.tags.map((tag) => (
                <span key={tag} className="sf-pill">
                  #{tag}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Publishing loading */}
      {step === 'publishing' && (
        <div className="sf-card sf-fade mb-4 px-4 py-5 text-center">
          <Spinner className="mx-auto mb-3" />
          <p className="text-sm text-[var(--ink-soft)]">记录打卡中...</p>
        </div>
      )}

      {error && (
        <div className="sf-note-card mb-4 px-4 py-3 text-sm text-[var(--danger)]">{error}</div>
      )}

      {/* CTA buttons */}
      {step === 'preview' && (
        <div className="sf-rise sf-rise-2 flex gap-3">
          <button
            onClick={() => router.back()}
            className="sf-btn-secondary flex-1"
          >
            返回修改
          </button>
          <button
            onClick={handleCheckQuality}
            disabled={submitting || checkinLoading || !!checkinLoadError || !content.trim()}
            className="sf-btn-primary flex-1"
          >
            {submitting ? '评估中...' : checkinLoading ? '加载中...' : checkinStatus === 'completed' ? '查看内容提示' : '查看发布提示'}
          </button>
        </div>
      )}

      {/* W1.4 多平台格式 + 导出 (fast path, visible whenever a draft exists) */}
      {content.trim() && (
        <div className="sf-soft-card sf-rise sf-rise-3 mt-6 px-5 py-4">
          <div className="mb-3">
            <p className="text-sm font-semibold text-[var(--ink)]">直接发到目标平台</p>
            <p className="mt-0.5 text-xs text-[var(--ink-muted)]">
              选平台 → 复制 → 粘贴，两步发出去。
            </p>
          </div>

          {/* Platform pills */}
          <div className="mb-3 flex flex-wrap gap-2">
            {PLATFORMS.map((p) => {
              const active = selectedPlatform === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => handleFormatForPlatform(p.id)}
                  disabled={formatting}
                  className={`rounded-full px-3.5 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
                    active
                      ? 'bg-[var(--ink)] text-white'
                      : 'border border-[var(--border-strong)] bg-white/70 text-[var(--ink-soft)] hover:bg-white'
                  }`}
                  title={p.hint}
                >
                  {p.label}
                </button>
              );
            })}
          </div>

          {/* Formatted preview */}
          {formatting && (
            <div className="sf-card px-3 py-3 text-center text-xs text-[var(--ink-muted)]">
              正在格式化...
            </div>
          )}
          {formatError && !formatting && (
            <div className="rounded-xl bg-[rgba(181,106,91,0.08)] px-3 py-2 text-xs text-[var(--danger)]">
              {formatError}
            </div>
          )}
          {formatted && !formatting && (
            <>
              <div className="sf-card relative px-4 py-3">
                <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words font-[inherit] text-sm leading-relaxed text-[var(--ink)]">
                  {formatted.text}
                </pre>
                {formatted.truncated && (
                  <span className="absolute right-2 top-2 rounded bg-[var(--highlight)] px-1.5 py-0.5 text-[10px] text-[var(--ink-soft)]">
                    已截断
                  </span>
                )}
              </div>
              <div className="mt-2 flex items-center justify-between text-[11px] text-[var(--ink-muted)]">
                <span>
                  平台: {PLATFORMS.find((p) => p.id === formatted.platform)?.label ?? formatted.platform}
                  {formatted.platform !== formatted.requested_platform && (
                    <span className="ml-1 text-[var(--danger)]">
                      (未知平台「{formatted.requested_platform}」,已用通用格式)
                    </span>
                  )}
                  · {formatted.char_count} 字
                </span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handleCopyFormatted}
                  className="sf-btn-primary min-h-11 flex-1"
                >
                  {copiedFormatted ? '✓ 已复制' : '复制到剪贴板'}
                </button>
                <button
                  type="button"
                  onClick={() => handleDownload('md')}
                  disabled={downloadingFormat !== null}
                  className="sf-btn-secondary min-h-11 px-4"
                >
                  {downloadingFormat === 'md' ? '下载中...' : '⬇ .md'}
                </button>
                <button
                  type="button"
                  onClick={() => handleDownload('txt')}
                  disabled={downloadingFormat !== null}
                  className="sf-btn-secondary min-h-11 px-4"
                >
                  {downloadingFormat === 'txt' ? '下载中...' : '⬇ .txt'}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {step === 'quality_result' && (
        <div className="mt-4 flex gap-3">
          {(qualityPass || checkinStatus === 'completed') && (
            <button
              onClick={() => setStep('preview')}
              className="sf-btn-secondary flex-1"
            >
              返回修改
            </button>
          )}
          {checkinStatus !== 'completed' ? (
            <button
              onClick={() => handleCompose(false)}
              disabled={submitting}
              className="sf-btn-primary flex-1"
            >
              {submitting ? '生成中...' : '生成图文素材'}
            </button>
          ) : (
            <Link
              href="/history?tab=completed"
              className="sf-btn-primary flex-1"
            >
              返回历史
            </Link>
          )}
        </div>
      )}

      {step === 'compose_ready' && checkinStatus !== 'completed' && (
        <div className="mt-4 flex gap-3">
          <button
            onClick={() => setStep('quality_result')}
            className="sf-btn-secondary flex-1"
          >
            返回修改
          </button>
          <button
            onClick={handlePublish}
            disabled={submitting || renderingImages}
            className="sf-btn-primary flex-1"
          >
            {submitting ? '记录中...' : '我已发到目标平台，确认打卡'}
          </button>
        </div>
      )}

      {/* W2.x bridge: from the canonical preview flow into the paste-to-cards
          side tool, so the user can render the same draft to image cards
          without re-pasting the text. The data crosses the navigation
          boundary via localStorage (URLs cap at ~2KB and a 20k-char draft
          blows past that). /image-cards clears the key on read. */}
      {step === 'compose_ready' && content.trim() && (
        <div className="sf-note-card mt-4 px-5 py-4">
          <p className="text-sm font-semibold text-[var(--ink)]">想要小红书卡片图？</p>
          <p className="mt-1 text-xs leading-5 text-[var(--ink-muted)]">
            顺发会把这份草稿带过去，预填正文和封面，点一下就能出图。
          </p>
          <button
            type="button"
            onClick={handleBridgeToImageCards}
            className="sf-btn-secondary mt-3 min-h-11 w-full"
          >
            用此草稿生成小红书卡片图 →
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
        <div className="flex h-screen items-center justify-center">
          <Spinner />
        </div>
      }>
        <PreviewContent />
      </Suspense>
    </ProtectedRoute>
  );
}
