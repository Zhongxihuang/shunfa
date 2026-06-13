'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import Navbar from '@/components/Navbar';
import { api, getErrorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { isDevPreviewToken } from '@/lib/devPreview';

interface ReminderStatus {
  reminder_enabled: boolean;
  reminder_time: string | null;
}

interface ApiKeyStatus {
  configured: boolean;
  preview: string | null;
}

function SettingsContent() {
  const router = useRouter();
  const { token, user, apiKeyConfigured, setApiKeyConfigured, logout } = useAuth();

  // Reminder settings
  const [enabled, setEnabled] = useState(false);
  const [time, setTime] = useState('09:00');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [reminderError, setReminderError] = useState('');

  // BYOK
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [apiKeyStatus, setApiKeyStatus] = useState<ApiKeyStatus>({ configured: false, preview: null });
  const [apiKeySaving, setApiKeySaving] = useState(false);
  const [apiKeySaved, setApiKeySaved] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (isDevPreviewToken(token)) {
      setEnabled(user?.reminder_enabled ?? false);
      setTime(user?.reminder_time ?? '09:00');
      setApiKeyStatus({ configured: true, preview: '...demo' });
      return;
    }
    api.get<ReminderStatus>('/api/reminder_status')
      .then((d) => {
        setEnabled(d.reminder_enabled);
        setTime(d.reminder_time ?? '09:00');
      })
      .catch(() => { /* keep defaults; saving still works */ });
    api.get<ApiKeyStatus>('/api/user/api_key/status')
      .then((d) => {
        setApiKeyStatus(d);
      })
      .catch(() => { /* the auth context already tracks configured-state */ });
  }, [token, user]);

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    setReminderError('');
    try {
      if (!isDevPreviewToken(token)) {
        await api.post('/api/reminder', { reminder_enabled: enabled, reminder_time: enabled ? time : null });
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e: unknown) {
      setReminderError(getErrorMessage(e, '保存失败，请重试'));
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveApiKey() {
    const key = apiKeyInput.trim();
    if (!key) return;
    setApiKeySaving(true);
    setApiKeySaved(false);
    setError('');
    try {
      if (!isDevPreviewToken(token)) {
        await api.post<ApiKeyStatus>('/api/user/api_key', { api_key: key });
      }
      const preview = `...${key.slice(-4)}`;
      setApiKeyStatus({ configured: true, preview });
      setApiKeyConfigured(true);
      setApiKeyInput('');
      setShowApiKey(false);
      setApiKeySaved(true);
      setTimeout(() => setApiKeySaved(false), 2000);
    } catch (e: unknown) {
      setError(getErrorMessage(e, '保存失败，请检查 Key 后重试'));
    } finally {
      setApiKeySaving(false);
    }
  }

  async function handleDeleteApiKey() {
    setError('');
    try {
      if (!isDevPreviewToken(token)) {
        await api.delete('/api/user/api_key');
      }
      localStorage.removeItem('shunfa_api_key');
      setApiKeyStatus({ configured: false, preview: null });
      setApiKeyConfigured(false);
    } catch (e: unknown) {
      setError(getErrorMessage(e, '删除失败，请重试'));
    }
  }

  return (
    <div className="sf-shell md:max-w-4xl xl:max-w-4xl">
      <div className="sf-rise mb-6 flex items-center gap-3">
        <button
          onClick={() => router.back()}
          aria-label="返回上一页"
          className="sf-btn-secondary h-10 min-h-10 w-10 px-0"
        >
          ←
        </button>
        <div>
          <p className="sf-eyebrow">设置</p>
          <h1 className="sf-display mt-1 text-2xl font-semibold text-[var(--ink)]">让顺发顺手一点</h1>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
      {/* DeepSeek API Key (BYOK) */}
      <section className="sf-card sf-rise sf-rise-1 p-6">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="sf-display text-xl font-semibold text-[var(--ink)]">DeepSeek API Key</h2>
            <p className="mt-1 text-xs leading-5 text-[var(--ink-muted)]">用于驱动 AI 选题和内容生成</p>
          </div>
          <span className={`sf-pill ${apiKeyConfigured ? 'sf-pill-accent' : ''}`} style={apiKeyConfigured ? undefined : { color: 'var(--danger)', borderColor: 'rgba(181, 106, 91, 0.3)' }}>
            {apiKeyConfigured ? (apiKeyStatus.preview ?? '已配置') : '未配置'}
          </span>
        </div>

        {error && <p className="mb-3 text-sm text-[var(--danger)]">{error}</p>}
        {!apiKeyStatus.configured || showApiKey ? (
          <div className="space-y-3">
            <input
              type="password"
              value={apiKeyInput}
              onChange={(e) => setApiKeyInput(e.target.value)}
              placeholder="sk-..."
              autoComplete="off"
              className="sf-input"
            />
            <p className="text-xs leading-5 text-[var(--ink-muted)]">
              前往{' '}
              <a
                href="https://platform.deepseek.com/api_keys"
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-[var(--ink-soft)]"
              >
                platform.deepseek.com
              </a>{' '}
              免费获取。Key 仅加密存储在您自己的账号下，作者无法查看。
            </p>
            <div className="flex gap-2">
              <button
                onClick={handleSaveApiKey}
                disabled={apiKeySaving || !apiKeyInput.trim()}
                className="sf-btn-primary min-h-11 flex-1"
              >
                {apiKeySaving ? '保存中...' : apiKeySaved ? '已保存 ✓' : '保存 Key'}
              </button>
              {showApiKey && (
                <button
                  onClick={() => setShowApiKey(false)}
                  className="sf-btn-secondary min-h-11 px-4"
                >
                  取消
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="flex gap-2">
            <button
              onClick={() => setShowApiKey(true)}
              className="sf-btn-secondary min-h-11 flex-1"
            >
              更换 Key
            </button>
            <button
              onClick={handleDeleteApiKey}
              className="min-h-11 rounded-full border border-[rgba(181,106,91,0.3)] px-5 text-sm text-[var(--danger)] transition hover:bg-[rgba(181,106,91,0.06)]"
            >
              移除
            </button>
          </div>
        )}
      </section>

      {/* Reminder settings */}
      <section className="sf-card sf-rise sf-rise-2 space-y-5 p-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="sf-display text-xl font-semibold text-[var(--ink)]">每日提醒</h2>
            <p className="mt-1 text-xs leading-5 text-[var(--ink-muted)]">在设定时间提醒你写文章</p>
          </div>
          <button
            onClick={() => setEnabled(!enabled)}
            role="switch"
            aria-checked={enabled}
            aria-label="每日提醒开关"
            className={`relative h-6 w-12 flex-shrink-0 rounded-full transition-colors ${enabled ? 'bg-primary' : 'bg-[var(--border-strong)]'}`}
          >
            <span
              className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${enabled ? 'translate-x-6' : 'translate-x-0.5'}`}
            />
          </button>
        </div>

        {enabled && (
          <div className="sf-fade">
            <label htmlFor="reminder-time" className="mb-1.5 block text-sm font-medium text-[var(--ink-soft)]">提醒时间</label>
            <input
              id="reminder-time"
              type="time"
              value={time}
              onChange={(e) => setTime(e.target.value)}
              className="sf-input"
            />
          </div>
        )}

        {reminderError && <p className="text-sm text-[var(--danger)]">{reminderError}</p>}

        <button
          onClick={handleSave}
          disabled={saving}
          className="sf-btn-primary w-full"
        >
          {saving ? '保存中...' : saved ? '已保存 ✓' : '保存'}
        </button>
      </section>
      </div>

      <div className="sf-rise sf-rise-3 mt-6 border-t border-[var(--border)] pt-6">
        <button
          onClick={logout}
          className="min-h-12 w-full rounded-full border border-[rgba(181,106,91,0.3)] text-sm font-medium text-[var(--danger)] transition hover:bg-[rgba(181,106,91,0.06)]"
        >
          退出登录
        </button>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <ProtectedRoute>
      <SettingsContent />
      <Navbar />
    </ProtectedRoute>
  );
}
