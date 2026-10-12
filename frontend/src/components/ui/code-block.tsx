/**
 * Code block (Watermelon UI `code-block`), customized for AnalystOS:
 * - shiki core with only SQL + Python loaded on demand (no full bundle)
 * - a CSS-variables theme, so tokens follow the app's light/dark palette without re-highlighting
 * - Phosphor icons, inline copy confirmation (customized `inline-toast`), collapsible long code
 * - the original action-button/zod scaffolding removed
 */
import { CaretDownIcon, CaretUpIcon } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import type { HighlighterCore } from 'shiki/core'
import { InlineCopy } from '@/components/watermelon/inline-toast'
import { cn } from '@/lib/utils'

export type CodeLanguage = 'sql' | 'python' | 'text'

let highlighterPromise: Promise<HighlighterCore> | null = null

async function getHighlighter(): Promise<HighlighterCore> {
  if (!highlighterPromise) {
    highlighterPromise = (async () => {
      const [{ createHighlighterCore, createCssVariablesTheme }, { createJavaScriptRegexEngine }] = await Promise.all([
        import('shiki/core'),
        import('shiki/engine/javascript'),
      ])
      const theme = createCssVariablesTheme({ name: 'analystos', variablePrefix: '--shiki-', fontStyle: true })
      return createHighlighterCore({
        themes: [theme],
        langs: [import('shiki/langs/sql.mjs'), import('shiki/langs/python.mjs')],
        engine: createJavaScriptRegexEngine(),
      })
    })()
  }
  return highlighterPromise
}

const cache = new Map<string, string>()

function escapeHtml(code: string): string {
  return code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function plainHtml(code: string): string {
  return `<pre><code>${code
    .split('\n')
    .map((line) => `<span class="line">${escapeHtml(line)}</span>`)
    .join('\n')}</code></pre>`
}

const LANGUAGE_NAMES: Record<CodeLanguage, string> = { sql: 'SQL', python: 'Python', text: 'Text' }

export interface CodeBlockProps {
  code: string
  language?: CodeLanguage
  title?: string
  maxCollapsedLines?: number
  className?: string
  actions?: React.ReactNode
}

export function CodeBlock({
  code,
  language = 'text',
  title,
  maxCollapsedLines = 18,
  className,
  actions,
}: CodeBlockProps) {
  const key = `${language}::${code}`
  const [html, setHtml] = useState<string>(() => cache.get(key) ?? plainHtml(code))
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    const cached = cache.get(key)
    if (cached) {
      setHtml(cached)
      return
    }
    setHtml(plainHtml(code))
    if (language === 'text' || !code) return
    let cancelled = false
    getHighlighter()
      .then((highlighter) => {
        const out = highlighter.codeToHtml(code, { lang: language, theme: 'analystos' })
        cache.set(key, out)
        if (!cancelled) setHtml(out)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [code, key, language])

  const lineCount = code.split('\n').length
  const collapsible = lineCount > maxCollapsedLines
  const collapsed = collapsible && !expanded

  return (
    <div data-slot="code-block" className={cn('bg-surface-2 min-w-0 overflow-hidden rounded-lg border', className)}>
      <div className="flex items-center justify-between gap-2 border-b px-3 py-1">
        <span className="text-muted-foreground truncate text-xs">
          <span className="text-foreground font-medium">{LANGUAGE_NAMES[language]}</span>
          {title && <span className="ml-2">{title}</span>}
        </span>
        <span className="flex items-center gap-1">
          {actions}
          <InlineCopy text={code} />
        </span>
      </div>
      <div
        className={cn('code-surface overflow-x-auto', collapsed && 'max-h-72 overflow-y-hidden')}
        // shiki output is generated from escaped code tokens
        dangerouslySetInnerHTML={{ __html: html }}
      />
      {collapsible && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-ring/60 flex w-full items-center justify-center gap-1.5 border-t py-1.5 text-xs focus-visible:ring-2 focus-visible:outline-none"
          aria-expanded={expanded}
        >
          {collapsed ? <CaretDownIcon className="size-3.5" /> : <CaretUpIcon className="size-3.5" />}
          {collapsed ? `Show all ${lineCount} lines` : 'Collapse'}
        </button>
      )}
    </div>
  )
}
