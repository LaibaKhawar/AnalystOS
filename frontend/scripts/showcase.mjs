// Create the analyses shown in the static replay demo, through the real API and model (nothing is mocked).
// Usage: node scripts/showcase.mjs  (env: API_URL=http://localhost:8000, DEMO_EMAIL, DEMO_PASSWORD)
// Idempotent per conversation title: a conversation that already has a completed answer is skipped.

const API = process.env.API_URL ?? 'http://localhost:8000'
const EMAIL = process.env.DEMO_EMAIL ?? 'demo@analystos.dev'
const PASSWORD = process.env.DEMO_PASSWORD ?? 'analystos-demo-2026'

const SHOWCASE = [
  {
    source: 'Sales 2025-2026',
    title: 'Q3 vs Q2 performance',
    questions: [
      'Analyze our Q3 2026 performance versus Q2. Identify underperforming regions and the main reasons behind the decline.',
      'Which product contributed most to Lahore’s decline?',
    ],
  },
  {
    source: 'Sales 2025-2026',
    title: 'Karachi anomalies',
    questions: ['Were there any unusual days for Karachi’s revenue in August 2026?'],
  },
  {
    source: 'Sales 2025-2026',
    title: 'Enterprise revenue trend',
    questions: ['Plot monthly revenue for 2026 for Enterprise customers.'],
  },
  {
    source: 'SaaS subscriptions',
    title: 'Churn by plan',
    questions: ['Which plan has the highest churn rate?'],
  },
  {
    source: 'Marketing performance',
    title: 'Channel efficiency',
    questions: ['Which channel had the lowest cost per conversion?'],
  },
]

let token
const signIn = async () =>
  (token = (await call('POST', '/auth/login', { email: EMAIL, password: PASSWORD })).access_token)

async function call(method, route, body, retried = false) {
  const res = await fetch(`${API}/api${route}`, {
    method,
    headers: { 'content-type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401 && token && !retried) {
    await signIn() // access tokens last 30 minutes; a long showcase outlives one
    return call(method, route, body, true)
  }
  const data = res.status === 204 ? null : await res.json()
  if (!res.ok) throw new Error(`${method} ${route}: ${res.status} ${JSON.stringify(data)}`)
  return data
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function waitFor(analysisId) {
  for (;;) {
    const a = await call('GET', `/analyses/${analysisId}`)
    if (!['queued', 'running'].includes(a.status)) return a
    await sleep(5000)
  }
}

await signIn()
const sources = await call('GET', '/sources')
const byName = (name) => {
  const source = sources.find((s) => s.name === name)
  if (!source) throw new Error(`source ${name} not found`)
  return source
}

// A saved metric and a schedule, so those pages show real content too.
const sales = byName('Sales 2025-2026')
const metrics = await call('GET', `/sources/${sales.id}/metrics`)
if (!metrics.some((m) => m.name === 'aov')) {
  const [table] = await call('GET', `/sources/${sales.id}/tables`)
  await call('POST', `/sources/${sales.id}/metrics`, {
    name: 'aov',
    label: 'Average order value',
    description: 'Revenue per order line',
    table: table.name,
    expression: 'SUM(revenue) / COUNT(*)',
    format: 'currency',
    filters: [],
  })
  console.log('created saved metric aov')
}

const conversations = await call('GET', '/conversations')
for (const item of SHOWCASE) {
  const source = byName(item.source)
  let conversation = conversations.find((c) => c.title === item.title && c.data_source_id === source.id)
  if (conversation) {
    const done = await call('GET', `/conversations/${conversation.id}/analyses`)
    if (done.filter((a) => a.status === 'completed').length >= item.questions.length) {
      console.log(`skip ${item.title}`)
      continue
    }
  } else {
    conversation = await call('POST', '/conversations', { data_source_id: source.id, title: item.title })
  }
  for (const question of item.questions) {
    const started = Date.now()
    const analysis = await call('POST', `/conversations/${conversation.id}/ask`, { question })
    const result = await waitFor(analysis.id)
    console.log(`${result.status.padEnd(10)} ${((Date.now() - started) / 1000).toFixed(0)}s  ${question}`)
    if (result.status === 'completed') {
      await call('POST', `/analyses/${result.id}/report`).catch(() => undefined)
    }
  }
}

const schedules = await call('GET', '/schedules')
if (!schedules.some((s) => s.name === 'Daily revenue watch')) {
  const schedule = await call('POST', '/schedules', {
    data_source_id: sales.id,
    name: 'Daily revenue watch',
    question: 'Were there any unusual days for revenue by region in September 2026?',
    interval_minutes: 1440,
    alert_min_severity: 'medium',
    webhook_url: null,
    enabled: true,
  })
  const run = await call('POST', `/schedules/${schedule.id}/run`)
  const result = await waitFor(run.last_analysis_id)
  console.log(`schedule run ${result.status}`)
}
console.log('showcase ready')
