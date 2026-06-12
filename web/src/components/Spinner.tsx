'use client';

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

/**
 * Brand-accent spinner. Sizes map to h-6 / h-8 / h-10 so call sites can pick
 * one without re-deriving pixel sizes from utility classes.
 */
export default function Spinner({ size = 'md', className = '' }: SpinnerProps) {
  const sizeClass = size === 'sm' ? 'h-6 w-6' : size === 'lg' ? 'h-10 w-10' : 'h-8 w-8';
  return (
    <div
      className={`${sizeClass} animate-spin rounded-full border-4 border-primary border-t-transparent ${className}`}
      aria-label="加载中"
    />
  );
}
