import { cn } from '@/lib/utils'

/** The AnalystOS mark: an accent square with three rising bars. */
export function LogoMark({ className, title }: { className?: string; title?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      className={cn('size-6 shrink-0', className)}
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <rect width="32" height="32" rx="8" className="fill-brand" />
      <rect x="8" y="17" width="4" height="7" rx="1" className="fill-primary-foreground" />
      <rect x="14" y="13" width="4" height="11" rx="1" className="fill-primary-foreground" />
      <rect x="20" y="8" width="4" height="16" rx="1" className="fill-primary-foreground" />
    </svg>
  )
}

/** Wordmark: mark + "AnalystOS" set in Geist semibold. */
export function Logo({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn('text-foreground inline-flex items-center gap-2', className)}>
      <LogoMark />
      {!compact && <span className="text-[15px] font-semibold tracking-[-0.01em]">AnalystOS</span>}
      {compact && <span className="sr-only">AnalystOS</span>}
    </span>
  )
}
