/**
 * Mask-reveal headline. Each word rises from behind a clipping mask with a short stagger.
 * Motion inspired by OriginKit's "appear text" pattern; this is an original implementation.
 */
import { motion, useReducedMotion } from 'motion/react'
import { cn } from '@/lib/utils'

export function AppearText({ lines, className, delay = 0.1 }: { lines: string[]; className?: string; delay?: number }) {
  const reduce = useReducedMotion()
  let index = 0
  return (
    <span className={cn('block', className)}>
      {lines.map((line, li) => (
        <span key={li} className="inline sm:block">
          {line.split(' ').map((word, wi) => {
            const i = index++
            return (
              <span key={wi} className="inline-block overflow-hidden pb-[0.08em] align-bottom">
                <motion.span
                  className="inline-block"
                  initial={reduce ? false : { y: '105%', opacity: 0 }}
                  animate={{ y: '0%', opacity: 1 }}
                  transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: delay + i * 0.06 }}
                >
                  {word}
                </motion.span>
                {wi < line.split(' ').length - 1 && ' '}
              </span>
            )
          })}
          {li < lines.length - 1 && <span className="sm:hidden"> </span>}
        </span>
      ))}
    </span>
  )
}

export function FadeUp({
  children,
  className,
  delay = 0,
}: {
  children: React.ReactNode
  className?: string
  delay?: number
}) {
  const reduce = useReducedMotion()
  return (
    <motion.div
      className={className}
      initial={reduce ? false : { opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1], delay }}
    >
      {children}
    </motion.div>
  )
}
