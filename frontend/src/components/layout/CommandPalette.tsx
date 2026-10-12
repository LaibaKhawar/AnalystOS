import { ChatCenteredTextIcon, DatabaseIcon, TableIcon } from '@phosphor-icons/react'
import { useEffect } from 'react'
import { useNavigate } from 'react-router'
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command'
import { AnalysisStatusBadge } from '@/components/common/StatusBadge'
import { useRecentAnalyses } from '@/hooks/queries/analyses'
import { useSources } from '@/hooks/queries/sources'
import { useRoleAbilities } from '@/hooks/usePermissions'
import { visibleNavItems } from './nav'

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate()
  const sources = useSources()
  const analyses = useRecentAnalyses(20)
  const { isAdmin } = useRoleAbilities()

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        onOpenChange(!open)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onOpenChange])

  const go = (to: string) => {
    onOpenChange(false)
    navigate(to)
  }

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Jump to"
      description="Search datasets, analyses and pages"
    >
      <CommandInput placeholder="Search datasets, analyses, pages" aria-label="Search" />
      <CommandList>
        <CommandEmpty>No matches. Try a dataset name or part of a question.</CommandEmpty>
        <CommandGroup heading="Pages">
          {visibleNavItems(isAdmin, true).map((item) => (
            <CommandItem key={item.to} value={`page ${item.label}`} onSelect={() => go(item.to)}>
              <item.icon />
              {item.label}
            </CommandItem>
          ))}
        </CommandGroup>
        {(sources.data?.length ?? 0) > 0 && <CommandSeparator />}
        {(sources.data?.length ?? 0) > 0 && (
          <CommandGroup heading="Data sources">
            {sources.data?.map((s) => (
              <CommandItem key={s.id} value={`source ${s.name} ${s.id}`} onSelect={() => go(`/sources/${s.id}`)}>
                {s.kind === 'file' ? <TableIcon /> : <DatabaseIcon />}
                <span className="truncate">{s.name}</span>
                <span className="text-muted-foreground ml-auto text-xs">
                  {s.kind === 'file' ? s.file_type : s.kind}
                </span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {(analyses.data?.length ?? 0) > 0 && <CommandSeparator />}
        {(analyses.data?.length ?? 0) > 0 && (
          <CommandGroup heading="Analyses">
            {analyses.data?.map((a) => (
              <CommandItem
                key={a.id}
                value={`analysis ${a.question} ${a.id}`}
                onSelect={() => go(`/workspace/${a.conversation_id}?analysis=${a.id}`)}
              >
                <ChatCenteredTextIcon />
                <span className="truncate">{a.question}</span>
                <AnalysisStatusBadge status={a.status} className="ml-auto" />
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  )
}
