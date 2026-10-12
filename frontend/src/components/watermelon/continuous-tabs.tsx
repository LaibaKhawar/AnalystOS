/**
 * Continuous tabs (Watermelon UI `continuous-tabs-base`), customized for AnalystOS:
 * controlled value, WAI-ARIA tablist semantics with arrow-key navigation, theme tokens,
 * 8px radius, per-instance layoutId, and reduced-motion support.
 */
import { LayoutGroup, motion, useReducedMotion } from 'motion/react'
import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

export interface ContinuousTabItem<T extends string = string> {
  id: T
  label: ReactNode
  count?: number
}

interface ContinuousTabsProps<T extends string> {
  tabs: ContinuousTabItem<T>[]
  value: T
  onChange: (id: T) => void
  ariaLabel: string
  idPrefix?: string
  className?: string
  size?: 'sm' | 'md'
  stretch?: boolean
}

export function ContinuousTabs<T extends string>({
  tabs,
  value,
  onChange,
  ariaLabel,
  idPrefix,
  className,
  size = 'sm',
  stretch = false,
}: ContinuousTabsProps<T>) {
  const autoId = useId()
  const prefix = idPrefix ?? autoId
  const reduce = useReducedMotion()
  const refs = useRef<(HTMLButtonElement | null)[]>([])

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next = -1
    if (event.key === 'ArrowRight') next = (index + 1) % tabs.length
    else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = tabs.length - 1
    if (next >= 0) {
      event.preventDefault()
      onChange(tabs[next].id)
      refs.current[next]?.focus()
    }
  }

  return (
    <LayoutGroup id={prefix}>
      <div
        role="tablist"
        aria-label={ariaLabel}
        className={cn(
          'bg-muted/60 relative flex items-center gap-0.5 rounded-lg border p-0.5',
          stretch && 'w-full',
          className,
        )}
      >
        {tabs.map((tab, index) => {
          const active = value === tab.id
          return (
            <button
              key={tab.id}
              ref={(el) => {
                refs.current[index] = el
              }}
              type="button"
              role="tab"
              id={`${prefix}-tab-${tab.id}`}
              aria-selected={active}
              aria-controls={`${prefix}-panel-${tab.id}`}
              tabIndex={active ? 0 : -1}
              onClick={() => onChange(tab.id)}
              onKeyDown={(e) => onKeyDown(e, index)}
              className={cn(
                'focus-visible:ring-ring/60 relative rounded-[6px] font-medium transition-colors outline-none focus-visible:ring-2 active:scale-[0.98]',
                size === 'sm' ? 'h-7 px-2.5 text-xs' : 'h-8 px-3 text-sm',
                stretch && 'flex-1',
                active ? 'text-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {active && (
                <motion.span
                  layoutId="continuous-tab-pill"
                  transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 420, damping: 34, mass: 0.8 }}
                  className="bg-background ring-border absolute inset-0 rounded-[6px] shadow-xs ring-1"
                />
              )}
              <span className="relative z-10 inline-flex items-center gap-1.5">
                {tab.label}
                {typeof tab.count === 'number' && (
                  <span className="tabular bg-muted text-muted-foreground rounded-full px-1.5 text-[10px] leading-4">
                    {tab.count}
                  </span>
                )}
              </span>
            </button>
          )
        })}
      </div>
    </LayoutGroup>
  )
}
