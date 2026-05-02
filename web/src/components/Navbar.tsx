'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/lib/auth';

const tabs = [
  { href: '/', label: '首页', icon: '🏠' },
  { href: '/profile', label: '个人', icon: '👤' },
  { href: '/settings', label: '设置', icon: '⚙️' },
];

export default function Navbar() {
  const pathname = usePathname();
  const { apiKeyConfigured } = useAuth();

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 flex justify-around z-50">
      {tabs.map((tab) => {
        const active = pathname === tab.href;
        const isSettings = tab.href === '/settings';
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`relative flex flex-col items-center py-2 px-6 text-xs transition-colors ${
              active ? 'text-primary' : 'text-gray-500'
            }`}
          >
            <span className="text-xl mb-0.5">{tab.icon}</span>
            <span>{tab.label}</span>
            {isSettings && !apiKeyConfigured && (
              <span className="absolute top-1 right-4 w-2 h-2 bg-red-500 rounded-full" />
            )}
          </Link>
        );
      })}
    </nav>
  );
}
