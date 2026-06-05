import { DEV_PREVIEW_TOKEN } from './devPreview';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const DEFAULT_TIMEOUT_MS = Number(process.env.NEXT_PUBLIC_API_TIMEOUT_MS ?? 30000);
const GENERATION_TIMEOUT_MS = Number(process.env.NEXT_PUBLIC_GENERATION_TIMEOUT_MS ?? 90000);

interface RequestOptions extends RequestInit {
  timeoutMs?: number;
}

export interface ApiErrorData {
  error_code: string;
  message: string;
  request_id?: string;
}

export class ApiError extends Error {
  status: number;
  data: ApiErrorData;

  constructor(status: number, data: ApiErrorData) {
    super(data.message);
    this.status = status;
    this.data = data;
  }
}

function normalizeError(status: number, raw: unknown): ApiErrorData {
  if (raw && typeof raw === 'object') {
    const data = raw as {
      detail?: unknown;
      error_code?: unknown;
      message?: unknown;
      request_id?: unknown;
    };

    if (typeof data.error_code === 'string' && typeof data.message === 'string') {
      return {
        error_code: data.error_code,
        message: data.message,
        request_id: typeof data.request_id === 'string' ? data.request_id : undefined,
      };
    }

    if (typeof data.detail === 'string') {
      return {
        error_code: status === 401 ? 'invalid_token' : 'request_failed',
        message: data.detail,
      };
    }
  }

  return {
    error_code: status === 401 ? 'invalid_token' : 'request_failed',
    message: '请求失败，请稍后重试',
  };
}

export function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.data.message;
  if (error instanceof Error) return error.message || fallback;
  return fallback;
}

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('token');
}

function getUserApiKey(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('shunfa_api_key');
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const token = getToken();
  const userApiKey = getUserApiKey();
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options;

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

  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, { ...fetchOptions, headers, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(408, {
        error_code: 'request_timeout',
        message: '生成时间较长，请稍后刷新草稿或重试。',
      });
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeout);
  }

  if (res.status === 401) {
    if (token !== DEV_PREVIEW_TOKEN) {
      localStorage.removeItem('token');
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new Event('auth:expired'));
      }
    }
    throw new ApiError(401, { error_code: 'invalid_token', message: '登录已失效，请重新登录' });
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, normalizeError(res.status, err));
  }

  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, data?: unknown, options: RequestOptions = {}) =>
    request<T>(path, { ...options, method: 'POST', body: data ? JSON.stringify(data) : undefined }),
  postGeneration: <T>(path: string, data?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
      timeoutMs: GENERATION_TIMEOUT_MS,
    }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};
