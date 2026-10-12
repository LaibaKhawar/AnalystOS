import { useState } from 'react'
import type { Analysis } from '@/api/types'
import { ContinuousTabs } from '@/components/watermelon/continuous-tabs'
import { tabPanelProps } from '@/lib/tabs'
import { isActive } from '@/hooks/queries/analyses'
import { ExecutionsPanel } from './ExecutionsPanel'
import { FindingsPanel } from './FindingsPanel'
import { PlanPanel } from './PlanPanel'

type Tab = 'plan' | 'evidence' | 'executions'

export function Inspector({ analysis }: { analysis: Analysis | null }) {
  const [tab, setTab] = useState<Tab>('plan')
  if (!analysis)
    return (
      <p className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
        Ask a question to see its plan, the findings it computed, and every tool execution.
      </p>
    )
  return (
    <div className="flex flex-col gap-4">
      <ContinuousTabs<Tab>
        ariaLabel="Inspect analysis"
        idPrefix="inspector"
        value={tab}
        onChange={setTab}
        stretch
        tabs={[
          { id: 'plan', label: 'Plan' },
          { id: 'evidence', label: 'Evidence' },
          { id: 'executions', label: 'Executions' },
        ]}
      />
      <p className="text-muted-foreground truncate text-xs" title={analysis.question}>
        For: {analysis.question}
      </p>
      <div {...tabPanelProps('inspector', tab)}>
        {tab === 'plan' && <PlanPanel analysis={analysis} />}
        {tab === 'evidence' && <FindingsPanel analysisId={analysis.id} />}
        {tab === 'executions' && <ExecutionsPanel analysisId={analysis.id} active={isActive(analysis.status)} />}
      </div>
    </div>
  )
}
