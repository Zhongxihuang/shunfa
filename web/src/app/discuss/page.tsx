'use client';

import { useEffect, useRef, useState, Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import ChatBubble from '@/components/ChatBubble';
import { api, getErrorMessage } from '@/lib/api';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  time: string;
}

function now() {
  return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
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
  const bottomRef = useRef<HTMLDivElement>(null);

  const hasSentInit = useRef(false);

  useEffect(() => {
    if (!checkinId || hasSentInit.current) return;
    hasSentInit.current = true;
    setLoading(true);

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
          setMessages([{ role: 'assistant', content: '加载失败，请返回重试～', time: now() }]);
        }
      });
  }, [checkinId, angle, platform]);

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
      <div className="flex flex-shrink-0 items-center gap-3 border-b border-gray-200 bg-white px-4 py-3 md:rounded-t-2xl md:border-x md:border-t">
        <button onClick={() => router.back()} className="text-gray-500 hover:text-gray-700">
          ←
        </button>
        <div className="flex-1 min-w-0">
          <p className="text-xs text-gray-400">话题</p>
          <p className="text-sm font-medium text-gray-800 truncate">{topic}</p>
        </div>
      </div>

      {/* BYOK error banner */}
      {apiKeyMissing && (
        <div className="flex-shrink-0 px-4 py-3 bg-amber-50 border-b border-amber-200 text-sm text-amber-800">
          <span>需要配置 DeepSeek API Key 才能继续。</span>
          <Link href="/settings" className="ml-2 text-primary underline font-medium">
            前往设置 →
          </Link>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto bg-bg px-4 py-4 md:border-x md:border-gray-200 md:px-8">
        {messages.map((m, i) => (
          <ChatBubble key={i} role={m.role} content={m.content} time={m.time} />
        ))}
        {loading && (
          <div className="flex justify-start mb-3">
            <div className="bg-white rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
              <div className="flex gap-1">
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
        {showRefreshAngles && !loading && (
          <div className="flex justify-center mt-2 mb-1">
            <button
              onClick={handleRefreshAngles}
              className="text-xs text-gray-400 hover:text-primary underline"
            >
              换一批角度
            </button>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex-shrink-0 border-t border-gray-200 bg-white px-4 py-3 md:rounded-b-2xl md:border-x md:border-b md:px-8">
        <div className="flex gap-2 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={inputDisabled || loading}
            placeholder={inputDisabled ? '草稿已生成，即将跳转...' : '选一个角度编号，或输入你的想法'}
            rows={2}
            className="flex-1 resize-none px-3 py-2 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary disabled:opacity-50"
          />
          <button
            onClick={() => handleSend(input)}
            disabled={!input.trim() || loading || inputDisabled}
            className="px-4 py-2 bg-primary text-white rounded-xl text-sm font-medium disabled:opacity-40 hover:bg-primary-dark transition-colors flex-shrink-0"
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
      <Suspense fallback={<div className="flex items-center justify-center h-screen"><div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" /></div>}>
        <DiscussContent />
      </Suspense>
    </ProtectedRoute>
  );
}
