'use client';

import { useCallback, useEffect, useRef, useState, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import ChatBubble from '@/components/ChatBubble';
import Spinner from '@/components/Spinner';
import { api, getErrorMessage } from '@/lib/api';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  time: string;
}

function now() {
  return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

function TypingIndicator({ slow }: { slow: boolean }) {
  return (
    <div className="mb-3 flex justify-start">
      <div className="rounded-2xl rounded-bl-sm border border-[var(--border)] bg-[var(--surface-strong)] px-4 py-3 shadow-[var(--shadow-soft)]">
        <div className="flex gap-1">
          {[0, 150, 300].map((delay) => (
            <span
              key={delay}
              className="h-2 w-2 animate-bounce rounded-full bg-[var(--accent-strong)]"
              style={{ animationDelay: `${delay}ms` }}
            />
          ))}
        </div>
        {slow && (
          <p className="mt-2 text-sm text-[var(--ink-muted)]">AI 正在分析话题，通常需要 15-30 秒...</p>
        )}
      </div>
    </div>
  );
}

function DiscussContent() {
  const router = useRouter();
  const params = useSearchParams();
  const checkinId = parseInt(params.get('checkin_id') ?? '0');
  const topic = decodeURIComponent(params.get('topic') ?? '');
  const angle = params.get('angle') ?? '';
  const platform = params.get('platform') ?? 'xiaohongshu';

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [inputDisabled, setInputDisabled] = useState(false);
  const [showRefreshAngles, setShowRefreshAngles] = useState(false);
  const [apiKeyMissing, setApiKeyMissing] = useState(false);
  const [initFailed, setInitFailed] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const hasSentInit = useRef(false);

  const sendInit = useCallback(() => {
    setLoading(true);
    setInitFailed(false);

    api.postGeneration<{ reply: string; status: string; draft?: string }>('/api/generate_content', {
      checkin_id: checkinId,
      message: '__auto_suggest_angles__',
      angle,
      platform,
    })
      .then((data) => {
        setLoading(false);
        setMessages([{ role: 'assistant', content: data.reply, time: now() }]);
        setShowRefreshAngles(true);
      })
      .catch((e: unknown) => {
        setLoading(false);
        const detail = getErrorMessage(e, '');
        if (detail.includes('API Key')) {
          setApiKeyMissing(true);
        } else {
          setInitFailed(true);
        }
      });
  }, [checkinId, angle, platform]);

  useEffect(() => {
    if (!checkinId || hasSentInit.current) return;
    hasSentInit.current = true;
    sendInit();
  }, [checkinId, sendInit]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  async function handleSend(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    const newMessages: Message[] = [...messages, { role: 'user', content: trimmed, time: now() }];
    setMessages(newMessages);
    setInput('');
    setLoading(true);

    try {
      const data = await api.postGeneration<{ reply: string; status: string; draft?: string }>('/api/generate_content', {
        checkin_id: checkinId,
        message: trimmed,
        angle,
        platform,
      });

      setLoading(false);
      setMessages((prev) => [...prev, { role: 'assistant', content: data.reply, time: now() }]);

      // Once user sends a real message, hide angle refresh button
      if (trimmed !== '__refresh_angles__') {
        setShowRefreshAngles(false);
      }

      if (data.status === 'draft_ready' && data.draft) {
        setInputDisabled(true);
        sessionStorage.setItem('current_draft', data.draft);
        setTimeout(() => {
          router.push(`/preview?checkin_id=${checkinId}`);
        }, 1000);
      }
    } catch (e: unknown) {
      setLoading(false);
      const detail = getErrorMessage(e, '');
      if (detail.includes('API Key')) {
        setApiKeyMissing(true);
      } else {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: '抱歉，出了点问题，请重试～', time: now() },
        ]);
      }
    }
  }

  async function handleRefreshAngles() {
    if (loading) return;
    setLoading(true);
    try {
      const data = await api.postGeneration<{ reply: string; status: string }>('/api/generate_content', {
        checkin_id: checkinId,
        message: '__refresh_angles__',
        angle,
        platform,
      });
      setLoading(false);
      // Replace the last AI message with the new angle suggestion
      setMessages((prev) => {
        const last = [...prev];
        const lastAiIndex = last.length - 1;
        if (lastAiIndex >= 0 && last[lastAiIndex].role === 'assistant') {
          last[lastAiIndex] = { role: 'assistant', content: data.reply, time: now() };
        } else {
          last.push({ role: 'assistant', content: data.reply, time: now() });
        }
        return last;
      });
    } catch {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend(input);
    }
  }

  return (
    <div className="mx-auto flex h-[100dvh] max-w-md flex-col md:h-[calc(100dvh-3rem)] md:max-w-4xl md:py-6">
      {/* Header */}
      <div className="flex flex-shrink-0 items-center gap-3 border-b border-[var(--border)] bg-[var(--surface-strong)] px-4 py-3 md:rounded-t-2xl md:border-x md:border-t">
        <button
          onClick={() => router.back()}
          aria-label="返回上一页"
          className="flex h-8 w-8 items-center justify-center rounded-full text-[var(--ink-muted)] transition hover:bg-[var(--surface-muted)] hover:text-[var(--ink)]"
        >
          ←
        </button>
        <div className="min-w-0 flex-1">
          <p className="sf-eyebrow">深度讨论</p>
          <p className="truncate text-sm font-medium text-[var(--ink)]">{topic}</p>
        </div>
      </div>

      {/* BYOK error banner */}
      {apiKeyMissing && (
        <div className="flex-shrink-0 border-b border-[rgba(170,151,123,0.25)] bg-[var(--highlight)] px-4 py-3 text-sm text-[var(--ink-soft)]">
          <span>需要配置 DeepSeek API Key 才能继续。</span>
          <Link href="/settings" className="ml-2 font-medium text-primary-dark underline">
            前往设置 →
          </Link>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 md:border-x md:border-[var(--border)] md:px-8">
        {messages.map((m, i) => (
          <ChatBubble key={i} role={m.role} content={m.content} time={m.time} />
        ))}
        {loading && <TypingIndicator slow={messages.length === 0} />}
        {initFailed && !loading && (
          <div className="sf-note-card mx-auto max-w-sm px-5 py-4 text-center">
            <p className="text-sm font-medium text-[var(--ink)]">开场分析没有加载出来</p>
            <p className="mt-1 text-xs leading-5 text-[var(--ink-soft)]">可能是网络波动，重试一次通常就好。</p>
            <button onClick={sendInit} className="sf-btn-secondary mt-3 min-h-9 px-5 text-xs">
              重试
            </button>
          </div>
        )}
        {showRefreshAngles && !loading && (
          <div className="mb-1 mt-2 flex justify-center">
            <button
              onClick={handleRefreshAngles}
              className="text-xs text-[var(--ink-muted)] underline underline-offset-2 transition hover:text-primary-dark"
            >
              换一批角度
            </button>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex-shrink-0 border-t border-[var(--border)] bg-[var(--surface-strong)] px-4 py-3 md:rounded-b-2xl md:border-x md:border-b md:px-8">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={inputDisabled || loading}
            placeholder={inputDisabled ? '草稿已生成，即将跳转...' : '选一个角度编号，或输入你的想法'}
            rows={2}
            className="sf-textarea flex-1 rounded-xl px-3 py-2"
          />
          <button
            onClick={() => handleSend(input)}
            disabled={!input.trim() || loading || inputDisabled}
            className="sf-btn-primary min-h-11 flex-shrink-0 rounded-xl px-5"
          >
            发送
          </button>
        </div>
      </div>
    </div>
  );
}

export default function DiscussPage() {
  return (
    <ProtectedRoute>
      <Suspense fallback={<div className="flex h-screen items-center justify-center"><Spinner /></div>}>
        <DiscussContent />
      </Suspense>
    </ProtectedRoute>
  );
}
