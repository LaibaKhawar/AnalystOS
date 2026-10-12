import { EyeIcon, LockKeyIcon } from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

/** Inline explanation of why an action is unavailable (role or share level). Never a dead end: says who can help. */
export function AccessNotice({
  title,
  children,
  tone = 'locked',
  className,
  testId = 'access-notice',
}: {
  title: string
  children: ReactNode
  tone?: 'locked' | 'read'
  className?: string
  testId?: string
}) {
  const Icon = tone === 'read' ? EyeIcon : LockKeyIcon
  return (
    <div
      role="note"
      data-testid={testId}
      className={cn('bg-muted/40 flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-sm', className)}
    >
      <Icon className="text-muted-foreground mt-0.5 size-4 shrink-0" />
      <div className="min-w-0">
        <p className="text-foreground font-medium">{title}</p>
        <div className="text-muted-foreground mt-0.5">{children}</div>
      </div>
    </div>
  )
}
