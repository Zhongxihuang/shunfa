'use client';

import { useState, useCallback, useEffect } from 'react';
import Link from 'next/link';
import ProtectedRoute from '@/components/ProtectedRoute';
import Navbar from '@/components/Navbar';
import { api, getErrorMessage } from '@/lib/api';

type TemplateId = 'a' | 'b' | 'c';

interface PageModel {
  index: number;
  kind: 'cover' | 'body';
  title: string | null;
  paragraphs: string[];
}

interface CreateImageJobResponse {
  job_id: number;
  template: TemplateId;
  cover_title: string | null;
  pages: PageModel[];
  page_count: number;
  overflow: boolean;
  status: string;
  ai_title: string;
  ai_tags: string[];
}

interface RenderImageJobResponse {
  job_id: number;
  template: TemplateId;
  images: string[]; // base64-encoded PNGs
  page_count: number;
}

const TEMPLATES: Array<{ id: TemplateId; name: string; hint: string }> = [
  { id: 'a', name: '暖纸编辑', hint: '米色底 · 衬线标题' },
  { id: 'b', name: '瑞士现代', hint: '无衬线 · 几何' },
  { id: 'c', name: '撞色高定', hint: '深色高对比' },
];

function formatTagsForCopy(tags: string[]): string {
  return tags.map((t) => (t.startsWith('#') ? t : '#' + t)).join(' ');
}

function buildAllCopy(title: string, tags: string[]): string {
  const tagLine = formatTagsForCopy(tags);
  const titleLine = title.trim();
  if (titleLine && tagLine) return `${titleLine}\n\n${tagLine}`;
  return titleLine || tagLine;
}

function downloadDataUrl(dataUrl: string, filename: string): void {
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = filename;
  a.click();
}

function ImageCardsContent() {
  const [rawText, setRawText] = useState('');
  const [coverTitle, setCoverTitle] = useState('');
  const [template, setTemplate] = useState<TemplateId>('a');

  const [jobId, setJobId] = useState<number | null>(null);
  const [pages, setPages] = useState<PageModel[]>([]);
  const [pageCount, setPageCount] = useState(0);
  const [overflow, setOverflow] = useState(false);

  // AI copy is the value-add on top of deterministic pagination.
  const [aiTitle, setAiTitle] = useState('');
  const [aiTags, setAiTags] = useState<string[]>([]);

  const [images, setImages] = useState<string[]>([]);
  const [previewing, setPreviewing] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [error, setError] = useState('');

  const [copiedTitle, setCopiedTitle] = useState(false);
  const [copiedTags, setCopiedTags] = useState(false);
  const [copiedAll, setCopiedAll] = useState(false);

  // W2.x bridge: when the user came from the preview flow, the draft was
  // stashed in localStorage (URLs cap at ~2KB and a 20k-char draft blows
  // past that). Read it once on mount, pre-fill state, then clear the key
  // so a manual reload doesn't keep replaying it.
  const [prefilledFromDraft, setPrefilledFromDraft] = useState(false);
  useEffect(() => {
    try {
      const raw = localStorage.getItem('shunfa:image-cards-prefill');
      if (!raw) return;
      const data = JSON.parse(raw) as {
        raw_text?: string;
        cover_title?: string;
        ts?: number;
      };
      // Drop stale payloads (older than 5 min) so we don't surface a draft
      // the user has long since moved past.
      if (data?.ts && Date.now() - data.ts > 5 * 60 * 1000) {
        localStorage.removeItem('shunfa:image-cards-prefill');
        return;
      }
      if (typeof data?.raw_text === 'string' && data.raw_text.trim()) {
        setRawText(data.raw_text);
        if (typeof data.cover_title === 'string' && data.cover_title.trim()) {
          setCoverTitle(data.cover_title);
        }
        setPrefilledFromDraft(true);
      }
    } catch {
      // Malformed JSON or quota error — ignore and let the user paste manually.
    } finally {
      try { localStorage.removeItem('shunfa:image-cards-prefill'); } catch { /* noop */ }
    }
  }, []);

  const onPreview = useCallback(async () => {
    const trimmed = rawText.trim();
    if (!trimmed) {
      setError('请先粘贴正文');
      return;
    }
    setError('');
    setPreviewing(true);
    setImages([]);
    try {
      const res = await api.post<CreateImageJobResponse>('/api/image_jobs', {
        raw_text: trimmed,
        template,
        cover_title: coverTitle.trim() || null,
      });
      setJobId(res.job_id);
      setPages(res.pages);
      setPageCount(res.page_count);
      setOverflow(res.overflow);
      setAiTitle(res.ai_title || '');
      setAiTags(res.ai_tags || []);
    } catch (err) {
      setError(getErrorMessage(err, '生成预览失败，请重试'));
    } finally {
      setPreviewing(false);
    }
  }, [rawText, template, coverTitle]);

  const onRender = useCallback(async () => {
    if (!jobId) return;
    setError('');
    setRendering(true);
    try {
      const res = await api.postGeneration<RenderImageJobResponse>(
        `/api/image_jobs/${jobId}/render`,
        { template },
      );
      const dataUrls = (res.images || []).map((b64) => `data:image/png;base64,${b64}`);
      setImages(dataUrls);
    } catch (err) {
      setError(getErrorMessage(err, '图片渲染失败，请重试'));
    } finally {
      setRendering(false);
    }
  }, [jobId, template]);

  const copyText = useCallback(async (text: string, flag: 'title' | 'tags' | 'all') => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Fallback for older browsers / insecure contexts.
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand('copy');
      } catch {
        /* noop */
      }
      document.body.removeChild(ta);
    }
    if (flag === 'title') {
      setCopiedTitle(true);
      setTimeout(() => setCopiedTitle(false), 2000);
    } else if (flag === 'tags') {
      setCopiedTags(true);
      setTimeout(() => setCopiedTags(false), 2000);
    } else {
      setCopiedAll(true);
      setTimeout(() => setCopiedAll(false), 2000);
    }
  }, []);

  const aiTagsFormatted = formatTagsForCopy(aiTags);
  const hasAiCopy = !!(aiTitle.trim() || aiTags.length);
  const allCopy = buildAllCopy(aiTitle, aiTags);

  return (
    <div className="sf-shell">
      <div className="mx-auto max-w-3xl">
        <section className="sf-card sf-rise mb-5 p-6 md:p-8">
          <p className="sf-eyebrow">工具</p>
          <h1 className="sf-display mt-1 text-2xl font-bold text-[var(--ink)] md:text-3xl">
            粘贴正文，生成小红书卡片图
          </h1>
          <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">
            把写好的内容粘进来，自动分页 + AI 写标题/标签 + 高清 PNG 卡片，可直接保存到相册。
          </p>

          {prefilledFromDraft && (
            <div className="sf-notice sf-notice-ok sf-fade mt-4">
              ✓ 已从草稿预填正文和封面，点「生成预览」即可出图。
            </div>
          )}

          <textarea
            className="sf-textarea mt-5 min-h-[280px]"
            placeholder="粘贴正文…（第一段会作为封面金句，下方也能自定义）"
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            maxLength={20000}
          />

          <input
            className="sf-input mt-3"
            placeholder="可选：自定义封面文字"
            value={coverTitle}
            onChange={(e) => setCoverTitle(e.target.value)}
            maxLength={120}
          />

          <div className="mt-4 flex flex-wrap gap-2">
            {TEMPLATES.map((tpl) => (
              <button
                key={tpl.id}
                type="button"
                onClick={() => {
                  setTemplate(tpl.id);
                  setImages([]);
                }}
                className={`rounded-full border px-4 py-2 text-sm transition ${
                  template === tpl.id
                    ? 'border-[var(--ink)] bg-[var(--ink)] text-white'
                    : 'border-[var(--border)] bg-white/60 text-[var(--ink)] hover:border-[var(--border-strong)]'
                }`}
                title={tpl.hint}
              >
                {tpl.name}
              </button>
            ))}
          </div>

          <div className="mt-5 flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              onClick={onPreview}
              disabled={previewing}
              className="sf-btn-primary flex-1"
            >
              {previewing ? '生成中…' : '生成预览'}
            </button>
            {pages.length > 0 && (
              <button
                type="button"
                onClick={onRender}
                disabled={rendering}
                className="sf-btn-secondary flex-1"
              >
                {rendering ? '渲染中…' : '渲染高清图'}
              </button>
            )}
          </div>

          {error && (
            <div className="sf-notice sf-notice-danger sf-fade mt-4">
              {error}
            </div>
          )}

          {overflow && (
            <div className="sf-notice mt-4">
              内容较长（{pageCount} 页），建议精简到 8 页内。
            </div>
          )}
        </section>

        {/* Pagination preview (deterministic, no AI). */}
        {pages.length > 0 && (
          <section className="sf-card mb-5 p-5">
            <p className="sf-eyebrow">分页预览</p>
            <div className="mt-3 space-y-3">
              {pages.map((p) => (
                <div
                  key={p.index}
                  className="rounded-2xl border border-[var(--border)] bg-white/60 p-4"
                >
                  <p className="text-xs text-[var(--ink-muted)]">
                    {p.index} / {pageCount}
                  </p>
                  {p.kind === 'cover' ? (
                    <p className="mt-2 text-xl font-bold leading-snug text-[var(--ink)]">
                      {p.title}
                    </p>
                  ) : (
                    <div className="mt-2 space-y-1.5">
                      {p.paragraphs.map((para, idx) => (
                        <p key={idx} className="text-sm leading-6 text-[var(--ink)]">
                          {para}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Rendered images. */}
        {images.length > 0 && (
          <section className="sf-card mb-5 p-5">
            <p className="sf-eyebrow">高清卡片（点击保存）</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {images.map((dataUrl, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => downloadDataUrl(dataUrl, `shunfa-card-${idx + 1}.png`)}
                  className="block overflow-hidden rounded-2xl border border-[var(--border)] bg-white/40 transition hover:border-[var(--border-strong)]"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element -- PNGs are client-rendered data URLs from html2canvas. */}
                  <img
                    src={dataUrl}
                    alt={`card-${idx + 1}`}
                    className="block w-full"
                  />
                </button>
              ))}
            </div>
            <p className="mt-3 text-center text-xs text-[var(--ink-muted)]">
              点击图片下载 PNG
            </p>
          </section>
        )}

        {/* AI copy — the value-add layer. */}
        {hasAiCopy && (
          <section className="sf-card mb-5 p-5">
            <p className="sf-eyebrow">AI 文案（去小红书粘贴）</p>

            {aiTitle.trim() && (
              <div className="mt-3 flex items-start gap-3">
                <span className="sf-pill mt-0.5 flex-none">
                  标题
                </span>
                <p className="flex-1 text-base font-semibold leading-7 text-[var(--ink)]">
                  {aiTitle}
                </p>
                <button
                  type="button"
                  onClick={() => copyText(aiTitle.trim(), 'title')}
                  className="flex-none rounded-full border border-primary px-3 py-1 text-xs font-medium text-primary-dark transition hover:bg-primary/5"
                >
                  {copiedTitle ? '已复制 ✓' : '复制'}
                </button>
              </div>
            )}

            {aiTagsFormatted && (
              <div className="mt-3 flex items-start gap-3">
                <span className="sf-pill mt-0.5 flex-none">
                  标签
                </span>
                <p className="flex-1 text-sm leading-7 text-[var(--ink-soft)]">
                  {aiTagsFormatted}
                </p>
                <button
                  type="button"
                  onClick={() => copyText(aiTagsFormatted, 'tags')}
                  className="flex-none rounded-full border border-primary px-3 py-1 text-xs font-medium text-primary-dark transition hover:bg-primary/5"
                >
                  {copiedTags ? '已复制 ✓' : '复制'}
                </button>
              </div>
            )}

            {allCopy && (
              <button
                type="button"
                onClick={() => copyText(allCopy, 'all')}
                className="sf-btn-primary mt-4 min-h-11 w-full"
              >
                {copiedAll ? '标题+标签已复制 ✓' : '一键复制标题+标签'}
              </button>
            )}
          </section>
        )}

        {pages.length > 0 && !hasAiCopy && (
          <section className="sf-note-card mb-5 px-5 py-3 text-sm text-[var(--ink-soft)]">
            AI 文案本次未生成（可能 LLM 暂时不可用），可手动写或重试。
          </section>
        )}

        <p className="pb-4 text-center text-xs text-[var(--ink-muted)]">
          <Link href="/" className="underline hover:text-[var(--ink-soft)]">
            返回首页
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function ImageCardsPage() {
  return (
    <ProtectedRoute>
      <ImageCardsContent />
      <Navbar />
    </ProtectedRoute>
  );
}
