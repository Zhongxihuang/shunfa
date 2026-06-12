'use client';

import { useAuth } from '@/lib/auth';

interface AuthFailNoticeProps {
  /** Custom message shown when the user's session has expired. */
  message?: string;
  /** Whether the surrounding list-section should keep showing its empty
   *  state (default) or hide it because we know we don't have data. */
  compact?: boolean;
}

/**
 * Banner used by data-loading pages to offer a one-click path back to /login
 * when the API returns 401. The api.ts interceptor already clears the token
 * and dispatches `auth:expired` (which AuthProvider listens for and routes to
 * /login), so this is a redundant-but-clearer affordance for inline error
 * states. Calling logout() here is the same path the 401 listener takes, so
 * we don't double up — clicking the button just makes the redirect explicit.
 */
export default function AuthFailNotice({ message, compact = true }: AuthFailNoticeProps) {
  const { logout } = useAuth();
  return (
    <div className={compact ? 'sf-note-card mb-4 px-4 py-3 text-sm' : 'sf-card mb-4 px-5 py-6'}>
      <p className={compact ? 'text-[var(--ink-soft)]' : 'text-sm font-semibold text-[var(--ink)]'}>
        {message ?? '登录状态异常，无法加载数据。'}
      </p>
      <button
        onClick={logout}
        className="mt-2 text-xs font-semibold text-primary-dark underline disabled:opacity-50"
      >
        重新登录
      </button>
    </div>
  );
}
