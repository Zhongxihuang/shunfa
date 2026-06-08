'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';

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
      const e = err as { data?: { detail?: string } };
      setError(e?.data?.detail ?? (mode === 'login' ? '用户名或密码错误' : '注册失败，请重试'));
    } finally {
      setSubmitting(false);
    }
  }

  if (isLoading) return null;

  return (
    <div className="min-h-screen bg-bg flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-sm p-8">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900">顺发</h1>
          <p className="text-gray-500 mt-2 text-sm">热点发文助手，从选题到发布</p>
        </div>

        {/* Tab switcher */}
        <div className="flex bg-gray-100 rounded-xl p-1 mb-6">
          {(['login', 'register'] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => { setMode(m); setError(''); }}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                mode === m ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'
              }`}
            >
              {m === 'login' ? '登录' : '注册'}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">用户名</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary"
              placeholder="字母、数字或下划线，3-50 位"
              autoFocus
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary"
              placeholder={mode === 'register' ? '至少 8 位' : '请输入密码'}
            />
          </div>

          {mode === 'register' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">确认密码</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary"
                placeholder="再输一次"
              />
            </div>
          )}

          {error && <p className="text-red-500 text-sm">{error}</p>}

          <button
            type="submit"
            disabled={submitting || !username || !password}
            className="w-full py-3 bg-primary text-white rounded-xl font-medium disabled:opacity-50 hover:bg-primary-dark transition-colors"
          >
            {submitting ? (mode === 'login' ? '登录中...' : '注册中...') : (mode === 'login' ? '登录' : '注册')}
          </button>
        </form>

        {mode === 'register' && (
          <p className="mt-4 text-xs text-gray-400 text-center">
            注册后需在「设置」页填入自己的 DeepSeek API Key 才能使用 AI 功能
          </p>
        )}

        {process.env.NODE_ENV === 'development' && (
          <div className="mt-6 text-center">
            <button
              onClick={devLogin}
              className="text-xs text-gray-400 hover:text-gray-500 underline underline-offset-2"
            >
              跳过登录（界面预览）
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
