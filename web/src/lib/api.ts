import { DEV_PREVIEW_TOKEN } from './devPreview';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('token');
}

function getUserApiKey(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('shunfa_api_key');
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const userApiKey = getUserApiKey();

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  if (userApiKey) {
    headers['X-User-Api-Key'] = userApiKey;
  }

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (res.status === 401) {
    if (token !== DEV_PREVIEW_TOKEN) {
      localStorage.removeItem('token');
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new Event('auth:expired'));
      }
    }
    throw Object.assign(new Error('Unauthorized'), {
      status: 401,
      data: { detail: '登录已失效，请重新登录' },
    });
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw Object.assign(new Error(err.detail ?? 'Request failed'), { status: res.status, data: err });
  }

  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: 'POST', body: data ? JSON.stringify(data) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};
