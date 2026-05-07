'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/lib/auth';

const tabs = [
  { href: '/', label: '首页', mark: 'H' },
  { href: '/profile', label: '个人', mark: 'P' },
  { href: '/settings', label: '设置', mark: 'S' },
];

export default function Navbar() {
  const pathname = usePathname();
  const { apiKeyConfigured } = useAuth();

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 border-t border-[var(--border)] bg-[rgba(255,253,250,0.9)] backdrop-blur-md md:bottom-auto md:top-4 md:left-1/2 md:right-auto md:-translate-x-1/2 md:rounded-full md:border md:shadow-[var(--shadow-soft)]">
      <div className="mx-auto flex max-w-md justify-around md:max-w-none md:gap-1 md:px-2">
      {tabs.map((tab) => {
        const active = pathname === tab.href;
        const isSettings = tab.href === '/settings';
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`relative flex min-w-20 flex-col items-center px-5 py-2.5 text-xs transition-colors md:min-w-24 md:flex-row md:justify-center md:gap-2 md:rounded-full md:px-4 ${
              active ? 'text-primary-dark' : 'text-[var(--ink-muted)]'
            }`}
          >
            <span className={`mb-1 flex h-6 w-6 items-center justify-center rounded-full border text-[10px] font-semibold md:mb-0 ${
              active
                ? 'border-primary/20 bg-primary/10 text-primary-dark'
                : 'border-[var(--border)] bg-white/60 text-[var(--ink-muted)]'
            }`}>
              {tab.mark}
            </span>
            <span>{tab.label}</span>
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
