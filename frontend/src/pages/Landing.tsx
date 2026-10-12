import { CpuIcon, LockKeyIcon, ShieldCheckIcon, TimerIcon, WifiSlashIcon } from '@phosphor-icons/react'
import { Link } from 'react-router'
import { ActivityFeed } from '@/components/analysis/ActivityFeed'
import { EvidenceContent } from '@/components/analysis/EvidenceContent'
import { Logo } from '@/components/brand/Logo'
import { ChartCard } from '@/components/charts/ChartCard'
import { Pill } from '@/components/common/StatusBadge'
import { AppearText, FadeUp } from '@/components/landing/AppearText'
import { BLOCKED_SQL, SAMPLE_CHART, SAMPLE_EVENTS, SAMPLE_EVIDENCE } from '@/components/landing/sample'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { Button } from '@/components/ui/button'
import { CodeBlock } from '@/components/ui/code-block'
import { StepIndicator } from '@/components/watermelon/step-indicator'
import { useAuth } from '@/providers/auth-context'

function SampleFrame({
  children,
  label = 'Sample data. Live component preview.',
}: {
  children: React.ReactNode
  label?: string
}) {
  return (
    <div className="bg-background relative rounded-lg border p-3 sm:p-4">
      <div className="mb-3 flex items-center justify-between">
        <Pill tone="neutral">{label}</Pill>
      </div>
      {children}
    </div>
  )
}

const LOOP = [
  {
    title: 'Plan',
    body: 'The question becomes an explicit plan of tool calls: aggregate, compare periods, detect anomalies, find drivers, chart.',
  },
  {
    title: 'Execute',
    body: 'Each step runs as validated SQL or sandboxed Python. Failed steps are repaired and retried, and the plan is revised when results call for it.',
  },
  {
    title: 'Verify',
    body: 'Every number in the drafted answer is matched to a computed finding. Statements that cannot be matched are rewritten or removed.',
  },
  {
    title: 'Report',
    body: 'You get the answer, the charts rebuilt from source rows, and an export that carries its own evidence.',
  },
]

export default function Landing() {
  const { isAuthenticated } = useAuth()
  const primary = isAuthenticated ? '/' : '/register'
  return (
    <div className="bg-background text-foreground min-h-dvh">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-8">
        <Link
          to="/welcome"
          aria-label="AnalystOS home"
          className="focus-visible:ring-ring/60 rounded-lg outline-none focus-visible:ring-2"
        >
          <Logo />
        </Link>
        <nav className="flex items-center gap-1 sm:gap-2" aria-label="Account">
          <ThemeToggle />
          {!isAuthenticated && (
            <Button asChild variant="ghost" className="hidden sm:inline-flex">
              <Link to="/login">Sign in</Link>
            </Button>
          )}
          <Button asChild>
            <Link to={primary}>Start analyzing</Link>
          </Button>
        </nav>
      </header>

      <main>
        <section className="mx-auto grid max-w-6xl grid-cols-1 items-center gap-10 px-4 pt-10 pb-16 sm:px-8 md:pt-16 lg:grid-cols-[1.15fr_1fr] lg:gap-12 lg:pt-20">
          <div>
            <h1 className="text-foreground text-[2rem] leading-[1.08] font-semibold tracking-[-0.035em] sm:text-5xl lg:text-[2.9rem] xl:text-[3.25rem]">
              <AppearText lines={['Answers you can audit,', 'down to the query.']} />
            </h1>
            <FadeUp delay={0.45}>
              <p className="text-muted-foreground mt-5 max-w-md text-base sm:text-lg">
                Ask business questions of your data. Every number is verified and traced to the SQL that produced it.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Button asChild size="lg" className="h-10 px-4">
                  <Link to={primary}>Start analyzing</Link>
                </Button>
                {!isAuthenticated && (
                  <Button asChild size="lg" variant="outline" className="h-10 px-4">
                    <Link to="/login">Sign in</Link>
                  </Button>
                )}
              </div>
              <p className="text-muted-foreground mt-4 text-xs">
                CSV, Excel, PostgreSQL, MySQL and SQLite. Runs with a local model at $0.0000 per question.
              </p>
            </FadeUp>
          </div>
          <FadeUp delay={0.3}>
            <SampleFrame>
              <ChartCard chart={SAMPLE_CHART} />
            </SampleFrame>
          </FadeUp>
        </section>

        <section className="bg-surface-2/60 border-t">
          <div className="mx-auto grid max-w-6xl grid-cols-1 gap-10 px-4 py-20 sm:px-8 lg:grid-cols-[1fr_1.25fr] lg:gap-14">
            <FadeUp className="lg:sticky lg:top-12 lg:self-start">
              <h2 className="text-foreground text-3xl font-semibold tracking-[-0.025em]">
                Every number comes with its receipt.
              </h2>
              <p className="text-muted-foreground mt-4 max-w-md">
                Select any statement in an answer and the evidence opens beside it: the finding it matched, the exact
                SQL that ran, the rows it returned and when it ran. Percentages are recomputed from their inputs before
                they are allowed to stay.
              </p>
              <ul className="text-foreground/90 mt-6 flex flex-col gap-2 text-sm">
                <li>Facts, interpretations and recommendations are kept apart.</li>
                <li>Unsupported numbers are rewritten or removed, never shown.</li>
                <li>Charts are rebuilt from source rows and hash-checked.</li>
              </ul>
            </FadeUp>
            <FadeUp delay={0.1}>
              <SampleFrame>
                <EvidenceContent data={SAMPLE_EVIDENCE} analysisId="sample" preview />
              </SampleFrame>
            </FadeUp>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-20 sm:px-8">
          <FadeUp>
            <h2 className="text-foreground max-w-2xl text-3xl font-semibold tracking-[-0.025em]">
              Plan, execute, verify. Then answer.
            </h2>
            <p className="text-muted-foreground mt-3 max-w-2xl">
              You watch structured progress while it works: which step is running, what failed and how it recovered. No
              hidden reasoning, just the work.
            </p>
          </FadeUp>
          <div className="mt-10 grid grid-cols-1 gap-10 lg:grid-cols-[1.2fr_1fr]">
            <dl className="grid grid-cols-1 gap-x-8 gap-y-8 sm:grid-cols-2">
              {LOOP.map((step, i) => (
                <FadeUp key={step.title} delay={i * 0.06}>
                  <dt className="text-foreground flex items-center gap-2 text-base font-medium">
                    <span className="bg-brand h-px w-5" aria-hidden="true" />
                    {step.title}
                  </dt>
                  <dd className="text-muted-foreground mt-2 text-sm">{step.body}</dd>
                </FadeUp>
              ))}
            </dl>
            <FadeUp delay={0.1}>
              <SampleFrame label="Sample progress feed">
                <div className="flex flex-col gap-4 pt-6">
                  <StepIndicator
                    steps={[
                      { id: 'a', label: 'Aggregate revenue by region', status: 'done' },
                      { id: 'b', label: 'Compare to prior year', status: 'done' },
                      { id: 'c', label: 'Create chart', status: 'done' },
                    ]}
                  />
                  <ActivityFeed events={SAMPLE_EVENTS} />
                </div>
              </SampleFrame>
            </FadeUp>
          </div>
        </section>

        <section className="border-t">
          <div className="mx-auto grid max-w-6xl grid-cols-1 gap-10 px-4 py-20 sm:px-8 lg:grid-cols-[1fr_1fr] lg:items-center">
            <FadeUp className="order-2 lg:order-1">
              <CodeBlock code={BLOCKED_SQL} language="sql" title="validation" />
            </FadeUp>
            <FadeUp className="order-1 lg:order-2">
              <h2 className="text-foreground text-3xl font-semibold tracking-[-0.025em]">Read-only by construction.</h2>
              <p className="text-muted-foreground mt-4 max-w-md">
                SQL is parsed before it touches your database. Python runs in a locked-down container. Your credentials
                stay encrypted.
              </p>
              <ul className="mt-6 grid gap-3 text-sm sm:grid-cols-2">
                <li className="flex items-start gap-2">
                  <ShieldCheckIcon className="text-brand mt-0.5 size-4" /> Single SELECT statements, row limit and
                  timeout
                </li>
                <li className="flex items-start gap-2">
                  <WifiSlashIcon className="text-brand mt-0.5 size-4" /> Sandbox with no network access
                </li>
                <li className="flex items-start gap-2">
                  <CpuIcon className="text-brand mt-0.5 size-4" /> 1 CPU and 512 MB per run
                </li>
                <li className="flex items-start gap-2">
                  <TimerIcon className="text-brand mt-0.5 size-4" /> 30 second hard limit
                </li>
                <li className="flex items-start gap-2 sm:col-span-2">
                  <LockKeyIcon className="text-brand mt-0.5 size-4" /> PII columns masked in previews and hidden from
                  analysis
                </li>
              </ul>
            </FadeUp>
          </div>
        </section>

        <section className="bg-surface-2/60 border-t">
          <div className="mx-auto flex max-w-6xl flex-col items-start gap-6 px-4 py-16 sm:px-8 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-foreground text-2xl font-semibold tracking-[-0.02em]">
                Bring a spreadsheet. Leave with an audited answer.
              </h2>
              <p className="text-muted-foreground mt-2">Upload a file, ask a question, check the work.</p>
            </div>
            <Button asChild size="lg" className="h-10 px-4">
              <Link to={primary}>Start analyzing</Link>
            </Button>
          </div>
        </section>
      </main>

      <footer className="text-muted-foreground mx-auto flex max-w-6xl flex-col gap-2 px-4 py-8 text-xs sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <Logo />
        <p>The analyst that shows its work.</p>
      </footer>
    </div>
  )
}
