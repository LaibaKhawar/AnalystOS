import { CheckCircleIcon, XCircleIcon } from '@phosphor-icons/react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import type { EvaluationCase } from '@/api/types'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { formatCell, formatDuration, noDashes } from '@/lib/format'

/** Only flat score values are shown; nested diagnostics stay in the analysis itself. */
function scalarScores(scores: Record<string, unknown> | null | undefined): [string, unknown][] {
  return Object.entries(scores ?? {}).filter(
    ([, v]) => v === null || ['number', 'boolean', 'string'].includes(typeof v),
  )
}

function short(value: unknown): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

export function CasesTable({ cases }: { cases: EvaluationCase[] }) {
  const [category, setCategory] = useState('all')
  const [result, setResult] = useState('all')
  const [search, setSearch] = useState('')
  const categories = useMemo(() => Array.from(new Set(cases.map((c) => c.category))).sort(), [cases])
  const rows = cases.filter(
    (c) =>
      (category === 'all' || c.category === category) &&
      (result === 'all' || (result === 'pass' ? c.passed : !c.passed)) &&
      (!search || c.question.toLowerCase().includes(search.toLowerCase())),
  )
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_auto_auto]">
        <div className="flex flex-col gap-1">
          <label htmlFor="case-search" className="text-muted-foreground text-xs">
            Search questions
          </label>
          <Input id="case-search" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="case-cat" className="text-muted-foreground text-xs">
            Category
          </label>
          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger id="case-cat" className="w-full sm:w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All categories</SelectItem>
              {categories.map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="case-res" className="text-muted-foreground text-xs">
            Result
          </label>
          <Select value={result} onValueChange={setResult}>
            <SelectTrigger id="case-res" className="w-full sm:w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="pass">Passed</SelectItem>
              <SelectItem value="fail">Failed</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <p className="text-muted-foreground text-xs">
        {rows.length} of {cases.length} cases
      </p>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full min-w-[900px] text-left text-xs">
          <thead className="bg-surface-2 text-muted-foreground">
            <tr>
              {['Result', 'Category', 'Question', 'Expected', 'Scores', 'Latency', 'Error', ''].map((h, i) => (
                <th key={i} scope="col" className="border-b px-3 py-2 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.id} className="border-b align-top last:border-b-0">
                <td className="px-3 py-2">
                  {c.passed ? (
                    <span className="text-brand-text inline-flex items-center gap-1">
                      <CheckCircleIcon weight="fill" className="size-3.5" />
                      Pass
                    </span>
                  ) : (
                    <span className="text-danger inline-flex items-center gap-1">
                      <XCircleIcon weight="fill" className="size-3.5" />
                      Fail
                    </span>
                  )}
                </td>
                <td className="text-foreground px-3 py-2">{c.category}</td>
                <td className="text-foreground min-w-56 px-3 py-2">{noDashes(c.question)}</td>
                <td className="text-muted-foreground max-w-48 truncate px-3 py-2 font-mono" title={short(c.expected)}>
                  {short(c.expected)}
                </td>
                <td className="text-muted-foreground px-3 py-2 font-mono">
                  {scalarScores(c.scores).map(([k, v]) => (
                    <div key={k} className="whitespace-nowrap">
                      {k}: <span className="text-foreground">{formatCell(v)}</span>
                    </div>
                  ))}
                </td>
                <td className="tabular text-foreground px-3 py-2">{formatDuration(c.latency_ms)}</td>
                <td className="text-danger max-w-48 px-3 py-2 break-words">{c.error ? noDashes(c.error) : ''}</td>
                <td className="px-3 py-2">
                  {c.analysis_id && (
                    <Link
                      className="text-brand-text whitespace-nowrap hover:underline"
                      to={`/workspace/by-analysis/${c.analysis_id}`}
                    >
                      Open
                    </Link>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <p className="text-muted-foreground px-3 py-6 text-center text-xs">No cases match these filters.</p>
        )}
      </div>
    </div>
  )
}
