'use client';

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api } from './api';
import { DEV_PREVIEW_TOKEN, isDevPreviewToken } from './devPreview';

interface UserStatus {
  id: number;
  streak: number;
  longest_streak: number;
  points: number;
  level: number;
  diamonds: number;
  reminder_time: string | null;
  reminder_enabled: boolean;
  last_checkin_date: string | null;
  today_completed: boolean;
  reminder_needed: boolean;
}

const MOCK_USER: UserStatus = {
  id: 1,
  streak: 7,
  longest_streak: 14,
  points: 320,
  level: 3,
  diamonds: 6,
  reminder_time: '09:00',
  reminder_enabled: true,
  last_checkin_date: null,
  today_completed: false,
  reminder_needed: false,
};

interface AuthContextValue {
  token: string | null;
  user: UserStatus | null;
  isLoading: boolean;
  apiKeyConfigured: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  devLogin: () => void;
  logout: () => void;
  refreshUser: () => Promise<void>;
  setApiKeyConfigured: (v: boolean) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [apiKeyConfigured, setApiKeyConfigured] = useState(false);

  const refreshUser = useCallback(async () => {
    if (isDevPreviewToken(localStorage.getItem('token'))) return;
    try {
      const status = await api.get<UserStatus>('/api/user_status');
      setUser(status);
    } catch {
      setToken(null);
      setUser(null);
      localStorage.removeItem('token');
    }
  }, []);

  const checkApiKeyStatus = useCallback(async () => {
    const localKey = localStorage.getItem('shunfa_api_key');
    if (localKey) {
      setApiKeyConfigured(true);
      return;
    }
    try {
      const status = await api.get<{ configured: boolean }>('/api/user/api_key/status');
      setApiKeyConfigured(status.configured);
    } catch {
      setApiKeyConfigured(false);
    }
  }, []);

  useEffect(() => {
    const stored = localStorage.getItem('token');
    if (isDevPreviewToken(stored)) {
      setToken(stored);
      setUser(MOCK_USER);
      setApiKeyConfigured(true);
      setIsLoading(false);
    } else if (stored) {
      setToken(stored);
      Promise.all([refreshUser(), checkApiKeyStatus()]).finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, [refreshUser, checkApiKeyStatus]);

  const login = useCallback(async (username: string, password: string) => {
    const data = await api.post<{ token: string; user: UserStatus }>('/api/auth_login', { username, password });
    localStorage.setItem('token', data.token);
    setToken(data.token);
    setUser(data.user);
    await checkApiKeyStatus();
    router.push('/');
  }, [router, checkApiKeyStatus]);

  const register = useCallback(async (username: string, password: string) => {
    const data = await api.post<{ token: string; user: UserStatus }>('/api/register', { username, password });
    localStorage.setItem('token', data.token);
    setToken(data.token);
    setUser(data.user);
    setApiKeyConfigured(false);
    router.push('/settings');
  }, [router]);

  const devLogin = useCallback(() => {
    localStorage.setItem('token', DEV_PREVIEW_TOKEN);
    setToken(DEV_PREVIEW_TOKEN);
    setUser(MOCK_USER);
    setApiKeyConfigured(true);
    router.push('/');
  }, [router]);

  const logout = useCallback(() => {
    localStorage.removeItem('token');
    localStorage.removeItem('shunfa_api_key');
    setToken(null);
    setUser(null);
    setApiKeyConfigured(false);
    router.push('/login');
  }, [router]);

  return (
    <AuthContext.Provider value={{
      token, user, isLoading, apiKeyConfigured,
      login, register, devLogin, logout, refreshUser, setApiKeyConfigured,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
