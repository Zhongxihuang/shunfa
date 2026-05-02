'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import Navbar from '@/components/Navbar';
import { api } from '@/lib/api';
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
  const { token, user, apiKeyConfigured, setApiKeyConfigured } = useAuth();

  // Reminder settings
  const [enabled, setEnabled] = useState(false);
  const [time, setTime] = useState('09:00');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // BYOK
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [apiKeyStatus, setApiKeyStatus] = useState<ApiKeyStatus>({ configured: false, preview: null });
  const [apiKeySaving, setApiKeySaving] = useState(false);
  const [apiKeySaved, setApiKeySaved] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);

  useEffect(() => {
    if (isDevPreviewToken(token)) {
      setEnabled(user?.reminder_enabled ?? false);
      setTime(user?.reminder_time ?? '09:00');
      setApiKeyStatus({ configured: true, preview: '...demo' });
      return;
    }
    api.get<ReminderStatus>('/api/reminder_status').then((d) => {
      setEnabled(d.reminder_enabled);
      setTime(d.reminder_time ?? '09:00');
    });
    api.get<ApiKeyStatus>('/api/user/api_key/status').then((d) => {
      setApiKeyStatus(d);
    });
    // Also check localStorage
    const localKey = localStorage.getItem('shunfa_api_key');
    if (localKey) {
      setApiKeyStatus({ configured: true, preview: `...${localKey.slice(-4)}` });
    }
  }, [token, user]);

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    try {
      if (!isDevPreviewToken(token)) {
        await api.post('/api/reminder', { reminder_enabled: enabled, reminder_time: enabled ? time : null });
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveApiKey() {
    const key = apiKeyInput.trim();
    if (!key) return;
    setApiKeySaving(true);
    setApiKeySaved(false);
    try {
      // Save to localStorage for immediate use
      localStorage.setItem('shunfa_api_key', key);
      // Save encrypted to backend
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
    } finally {
      setApiKeySaving(false);
    }
  }

  async function handleDeleteApiKey() {
    localStorage.removeItem('shunfa_api_key');
    if (!isDevPreviewToken(token)) {
      await api.delete('/api/user/api_key');
    }
    setApiKeyStatus({ configured: false, preview: null });
    setApiKeyConfigured(false);
  }

  return (
    <div className="max-w-md mx-auto px-4 pt-6 pb-24">
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => router.back()} className="text-gray-500 hover:text-gray-700">
          ←
        </button>
        <h1 className="text-xl font-bold text-gray-900">设置</h1>
      </div>

      {/* DeepSeek API Key (BYOK) */}
      <div className="bg-white rounded-2xl p-5 shadow-sm mb-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="font-medium text-gray-800">DeepSeek API Key</div>
            <div className="text-xs text-gray-500 mt-0.5">用于驱动 AI 选题和内容生成</div>
          </div>
          <span className={`text-xs font-medium px-2 py-1 rounded-full ${
            apiKeyConfigured ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-600'
          }`}>
            {apiKeyConfigured ? (apiKeyStatus.preview ?? '已配置') : '未配置'}
          </span>
        </div>

        {!apiKeyStatus.configured || showApiKey ? (
          <div className="space-y-3">
            <input
              type="password"
              value={apiKeyInput}
              onChange={(e) => setApiKeyInput(e.target.value)}
              placeholder="sk-..."
              className="w-full px-4 py-3 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary"
            />
            <p className="text-xs text-gray-400">
              前往{' '}
              <a
                href="https://platform.deepseek.com/api_keys"
                target="_blank"
                rel="noopener noreferrer"
                className="underline"
              >
                platform.deepseek.com
              </a>{' '}
              免费获取。Key 仅加密存储在您自己的账号下，作者无法查看。
            </p>
            <div className="flex gap-2">
              <button
                onClick={handleSaveApiKey}
                disabled={apiKeySaving || !apiKeyInput.trim()}
                className="flex-1 py-2.5 bg-primary text-white rounded-xl text-sm font-medium disabled:opacity-50 hover:bg-primary-dark transition-colors"
              >
                {apiKeySaving ? '保存中...' : apiKeySaved ? '已保存 ✓' : '保存 Key'}
              </button>
              {showApiKey && (
                <button
                  onClick={() => setShowApiKey(false)}
                  className="px-4 py-2.5 border border-gray-300 rounded-xl text-sm text-gray-600"
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
              className="flex-1 py-2.5 border border-gray-300 rounded-xl text-sm text-gray-700 hover:bg-gray-50 transition-colors"
            >
              更换 Key
            </button>
            <button
              onClick={handleDeleteApiKey}
              className="px-4 py-2.5 border border-red-200 rounded-xl text-sm text-red-500 hover:bg-red-50 transition-colors"
            >
              移除
            </button>
          </div>
        )}
      </div>

      {/* Reminder settings */}
      <div className="bg-white rounded-2xl p-5 shadow-sm space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-medium text-gray-800">每日提醒</div>
            <div className="text-xs text-gray-500">在设定时间提醒你写文章</div>
          </div>
          <button
            onClick={() => setEnabled(!enabled)}
            className={`w-12 h-6 rounded-full transition-colors relative ${enabled ? 'bg-primary' : 'bg-gray-300'}`}
          >
            <span
              className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${enabled ? 'translate-x-6' : 'translate-x-0.5'}`}
            />
          </button>
        </div>

        {enabled && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">提醒时间</label>
            <input
              type="time"
              value={time}
              onChange={(e) => setTime(e.target.value)}
              className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary"
            />
          </div>
        )}

        <button
          onClick={handleSave}
          disabled={saving}
          className="w-full py-3 bg-primary text-white rounded-xl font-medium disabled:opacity-50 hover:bg-primary-dark transition-colors"
        >
          {saving ? '保存中...' : saved ? '已保存 ✓' : '保存'}
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
