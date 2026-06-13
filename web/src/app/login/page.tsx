'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { ApiError, getErrorMessage } from '@/lib/api';

type Mode = 'login' | 'register';

export default function LoginPage() {
  const { login, register, devLogin, token, isLoading } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<Mode>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isLoading && token) {
      router.push('/');
    }
  }, [isLoading, token, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');

    if (mode === 'register' && password !== confirmPassword) {
      setError('两次密码不一致');
      return;
    }
    if (mode === 'register' && password.length < 8) {
      setError('密码至少 8 位');
      return;
    }

    setSubmitting(true);
    try {
      if (mode === 'login') {
        await login(username, password);
      } else {
        await register(username, password);
      }
    } catch (err: unknown) {
      // api.ts rewrites every 401 into "登录已失效" for session-expiry UX; on
      // the login form itself a 401 just means wrong credentials.
      if (err instanceof ApiError && err.status === 401) {
        setError(mode === 'login' ? '用户名或密码错误' : '注册失败，请重试');
      } else {
        setError(getErrorMessage(err, mode === 'login' ? '登录失败，请重试' : '注册失败，请重试'));
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (isLoading) return null;

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="sf-rise w-full max-w-sm">
        <div className="mb-8 text-center">
          <span className="sf-eyebrow">每日一条 · 从热点到发布</span>
          <h1 className="sf-display mt-3 text-5xl font-bold text-[var(--ink)]">顺发</h1>
          <p className="mt-3 text-sm leading-6 text-[var(--ink-soft)]">选一个热点，形成一个判断，发出去。</p>
        </div>

        <div className="sf-card p-7">
          {/* Tab switcher */}
          <div className="mb-6 flex rounded-full border border-[var(--border)] bg-[var(--surface-muted)] p-1">
            {(['login', 'register'] as Mode[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => { setMode(m); setError(''); }}
                className={`flex-1 rounded-full py-2 text-sm font-medium transition-colors ${
                  mode === m
                    ? 'bg-[var(--ink)] text-white shadow-sm'
                    : 'text-[var(--ink-muted)] hover:text-[var(--ink)]'
                }`}
              >
                {m === 'login' ? '登录' : '注册'}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="username" className="mb-1.5 block text-sm font-medium text-[var(--ink-soft)]">用户名</label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="sf-input"
                placeholder="字母、数字或下划线，3-50 位"
                autoComplete="username"
                autoFocus
              />
            </div>

            <div>
              <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-[var(--ink-soft)]">密码</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="sf-input"
                placeholder={mode === 'register' ? '至少 8 位' : '请输入密码'}
                autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
              />
            </div>

            {mode === 'register' && (
              <div className="sf-fade">
                <label htmlFor="confirm-password" className="mb-1.5 block text-sm font-medium text-[var(--ink-soft)]">确认密码</label>
                <input
                  id="confirm-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="sf-input"
                  placeholder="再输一次"
                  autoComplete="new-password"
                />
              </div>
            )}

            {error && <p className="sf-fade text-sm text-[var(--danger)]">{error}</p>}

            <button
              type="submit"
              disabled={submitting || !username || !password}
              className="sf-btn-primary w-full"
            >
              {submitting ? (mode === 'login' ? '登录中...' : '注册中...') : (mode === 'login' ? '登录' : '注册')}
            </button>
          </form>

          {mode === 'register' && (
            <p className="mt-4 text-center text-xs leading-5 text-[var(--ink-muted)]">
              注册后需在「设置」页填入自己的 DeepSeek API Key 才能使用 AI 功能
            </p>
          )}

          {process.env.NODE_ENV === 'development' && (
            <div className="mt-6 text-center">
              <button
                onClick={devLogin}
                className="text-xs text-[var(--ink-muted)] underline underline-offset-2 hover:text-[var(--ink-soft)]"
              >
                跳过登录（界面预览）
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
