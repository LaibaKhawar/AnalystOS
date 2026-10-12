import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { followAnalysis } from '@/api/sse'
import type { Analysis, AnalysisEvent } from '@/api/types'
import { qk } from './queries/keys'
import { isActive } from './queries/analyses'

const REFRESH_ON = new Set(['plan', 'replan', 'step_started', 'step_completed', 'step_failed', 'step_skipped'])

export interface AnalysisStream {
  events: AnalysisEvent[]
  mode: 'stream' | 'polling' | 'idle'
}

/**
 * While an analysis is queued or running, follow its progress events (SSE with reconnect and a
 * polling fallback) and keep the cached analysis fresh. When it ends, refresh everything derived from it.
 */
export function useAnalysisStream(analysis: Analysis | undefined): AnalysisStream {
  const client = useQueryClient()
  const [events, setEvents] = useState<AnalysisEvent[]>([])
  const [mode, setMode] = useState<AnalysisStream['mode']>('idle')
  const refreshTimer = useRef<number | undefined>(undefined)
  const id = analysis?.id
  const active = isActive(analysis?.status)

  useEffect(() => {
    if (!id || !active) return
    setEvents([])
    setMode('stream')
    const refreshAnalysis = () => {
      window.clearTimeout(refreshTimer.current)
      refreshTimer.current = window.setTimeout(() => {
        void client.invalidateQueries({ queryKey: qk.analysis(id) })
        void client.invalidateQueries({ queryKey: qk.executions(id) })
      }, 250)
    }
    const stop = followAnalysis(id, 0, {
      onEvent: (event) => {
        setEvents((prev) => [...prev, event])
        if (REFRESH_ON.has(event.type)) refreshAnalysis()
      },
      onModeChange: (next) => setMode(next),
      onEnd: () => {
        setMode('idle')
        window.clearTimeout(refreshTimer.current)
        void client.invalidateQueries({ queryKey: ['analysis', id] })
        void client.invalidateQueries({ queryKey: qk.analysesAll })
        void client.invalidateQueries({ queryKey: qk.dashboard })
        void client.invalidateQueries({ queryKey: qk.reports })
        if (analysis?.conversation_id) {
          void client.invalidateQueries({ queryKey: qk.conversationAnalyses(analysis.conversation_id) })
          void client.invalidateQueries({ queryKey: qk.conversation(analysis.conversation_id) })
        }
      },
    })
    return () => {
      stop()
      window.clearTimeout(refreshTimer.current)
    }
    // analysis.conversation_id is stable for a given id
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, active, client])

  return { events, mode }
}
