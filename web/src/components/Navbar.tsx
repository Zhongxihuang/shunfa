'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/lib/auth';

interface TabIconProps {
  className?: string;
}

function HomeIcon({ className }: TabIconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5.5 9.5V20a1 1 0 0 0 1 1H10v-5.5h4V21h3.5a1 1 0 0 0 1-1V9.5" />
    </svg>
  );
}

function DraftIcon({ className }: TabIconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
      <path d="M9 13h6M9 17h4" />
    </svg>
  );
}

function HistoryIcon({ className }: TabIconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.5 2" />
    </svg>
  );
}

function SettingsIcon({ className }: TabIconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="3.2" />
      <path d="M19.4 13.5a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V19.6a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1.11-1.56 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H4.4a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.56-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h.08a1.7 1.7 0 0 0 1.03-1.56V4.4a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v.08a1.7 1.7 0 0 0 1.56 1.03h.17a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.56 1.03z" />
    </svg>
  );
}

const tabs = [
  { href: '/', label: '首页', Icon: HomeIcon },
  { href: '/drafts', label: '草稿', Icon: DraftIcon },
  { href: '/history', label: '历史', Icon: HistoryIcon },
  { href: '/settings', label: '设置', Icon: SettingsIcon },
];

export default function Navbar() {
  const pathname = usePathname();
  const { apiKeyConfigured } = useAuth();

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 border-t border-[var(--border)] bg-[rgba(255,253,250,0.9)] backdrop-blur-md md:bottom-auto md:top-4 md:left-1/2 md:right-auto md:-translate-x-1/2 md:rounded-full md:border md:shadow-[var(--shadow-soft)]">
      <div className="mx-auto flex max-w-md justify-around md:max-w-none md:gap-1 md:px-2">
      {tabs.map((tab) => {
        const active = pathname === tab.href || (tab.href === '/history' && pathname === '/profile');
        const isSettings = tab.href === '/settings';
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? 'page' : undefined}
            className={`relative flex min-w-20 flex-col items-center px-5 py-2.5 text-xs transition-colors md:min-w-24 md:flex-row md:justify-center md:gap-2 md:rounded-full md:px-4 ${
              active ? 'text-primary-dark' : 'text-[var(--ink-muted)] hover:text-[var(--ink-soft)]'
            }`}
          >
            <span className={`mb-1 flex h-7 w-7 items-center justify-center rounded-full transition-colors md:mb-0 ${
              active ? 'bg-primary/10' : 'bg-transparent'
            }`}>
              <tab.Icon className="h-[18px] w-[18px]" />
            </span>
            <span className={active ? 'font-medium' : ''}>{tab.label}</span>
            {isSettings && !apiKeyConfigured && (
              <span className="absolute right-5 top-2 h-2 w-2 rounded-full bg-[var(--danger)]" />
            )}
          </Link>
        );
      })}
      </div>
    </nav>
  );
}
