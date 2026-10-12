import {
  CheckCircleIcon,
  CircleDashedIcon,
  ProhibitIcon,
  QuestionIcon,
  SpinnerGapIcon,
  WarningCircleIcon,
} from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export type Tone = 'success' | 'warning' | 'danger' | 'neutral' | 'brand'

const TONES: Record<Tone, string> = {
  success: 'bg-success-soft text-brand-text border-success/25',
  brand: 'bg-brand-soft text-brand-text border-brand/25',
  warning: 'bg-warning-soft text-warning border-warning/25',
  danger: 'bg-danger-soft text-danger border-danger/25',
  neutral: 'bg-muted text-muted-foreground border-border',
}

/** Small pill badge. Pills are reserved for status, per the design system. */
export function Pill({
  tone = 'neutral',
  icon,
  children,
  className,
}: {
  tone?: Tone
  icon?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex h-5 shrink-0 items-center gap-1 rounded-full border px-2 text-[11px] font-medium whitespace-nowrap [&_svg]:size-3',
        TONES[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  )
}

const ANALYSIS: Record<string, { label: string; tone: Tone; icon: ReactNode }> = {
  queued: { label: 'Queued', tone: 'neutral', icon: <CircleDashedIcon /> },
  running: { label: 'Running', tone: 'brand', icon: <SpinnerGapIcon className="motion-safe:animate-spin" /> },
  completed: { label: 'Completed', tone: 'success', icon: <CheckCircleIcon weight="fill" /> },
  failed: { label: 'Failed', tone: 'danger', icon: <WarningCircleIcon weight="fill" /> },
  cancelled: { label: 'Cancelled', tone: 'neutral', icon: <ProhibitIcon /> },
  needs_clarification: { label: 'Needs input', tone: 'warning', icon: <QuestionIcon weight="bold" /> },
}

export function AnalysisStatusBadge({ status, className }: { status: string; className?: string }) {
  const meta = ANALYSIS[status] ?? { label: status, tone: 'neutral' as Tone, icon: null }
  return (
    <Pill tone={meta.tone} icon={meta.icon} className={className}>
      {meta.label}
    </Pill>
  )
}

export function SourceStatusBadge({ status }: { status: string }) {
  if (status === 'ready')
    return (
      <Pill tone="success" icon={<CheckCircleIcon weight="fill" />}>
        Ready
      </Pill>
    )
  if (status === 'error')
    return (
      <Pill tone="danger" icon={<WarningCircleIcon weight="fill" />}>
        Error
      </Pill>
    )
  return <Pill tone="neutral">{status}</Pill>
}
