'use client';

interface SkeletonProps {
  className?: string;
}

/**
 * Shimmer placeholder. Single source of truth for the design system's
 * loading-block color so tokens can be retuned in one place.
 */
export function Skeleton({ className = '' }: SkeletonProps) {
  return <div className={`animate-pulse rounded-2xl bg-white/60 ${className}`} />;
}

interface SkeletonCardProps {
  /** Tailwind height class, e.g. "h-32", "h-40". */
  height?: string;
}

/** Common loading block for list-style pages. */
export default function SkeletonCard({ height = 'h-32' }: SkeletonCardProps) {
  return <Skeleton className={height} />;
}
