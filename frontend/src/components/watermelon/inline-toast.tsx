/**
 * Inline toast (Watermelon UI `inline-toast-base`), customized as a compact copy control:
 * the label morphs into an inline "Copied" confirmation in place, no floating toast.
 * Theme tokens, 8px radius, Phosphor icons, reduced-motion aware.
 */
import { CheckIcon, CopyIcon } from '@phosphor-icons/react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'

export function InlineCopy({
  text,
  label = 'Copy',
  className,
  duration = 1600,
}: {
  text: string
  label?: string
  className?: string
  duration?: number
}) {
  const [copied, setCopied] = useState(false)
  const [failed, setFailed] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  const reduce = useReducedMotion()

  useEffect(() => () => window.clearTimeout(timer.current), [])

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setFailed(false)
    } catch {
      setFailed(true)
    }
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      setCopied(false)
      setFailed(false)
    }, duration)
  }

  const state = copied ? 'copied' : failed ? 'failed' : 'idle'
  return (
    <button
      type="button"
      onClick={copy}
      aria-label={copied ? 'Copied' : `${label} to clipboard`}
      className={cn(
        'text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-ring/60 inline-flex h-7 items-center gap-1.5 overflow-hidden rounded-md px-2 text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:outline-none active:scale-[0.98]',
        copied && 'text-brand-text',
        className,
      )}
    >
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={state}
          initial={reduce ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduce ? { opacity: 0 } : { opacity: 0, y: -6 }}
          transition={{ type: 'spring', bounce: 0, duration: 0.3 }}
          className="inline-flex items-center gap-1.5"
        >
          {copied ? <CheckIcon className="size-3.5" weight="bold" /> : <CopyIcon className="size-3.5" />}
          {state === 'copied' ? 'Copied' : state === 'failed' ? 'Copy blocked' : label}
        </motion.span>
      </AnimatePresence>
      <span className="sr-only" aria-live="polite">
        {copied ? 'Copied to clipboard' : ''}
      </span>
    </button>
  )
}
