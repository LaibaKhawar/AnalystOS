import { Link, useLocation } from 'react-router'
import { cn } from '@/lib/utils'
import { NAV_ITEMS } from './nav'

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const { pathname } = useLocation()
  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5">
      {NAV_ITEMS.map((item) => {
        const active = item.match(pathname)
        const Icon = item.icon
        return (
          <Link
            key={item.to}
            to={item.to}
            onClick={onNavigate}
            aria-current={active ? 'page' : undefined}
            className={cn(
              'focus-visible:ring-ring/60 flex h-8 items-center gap-2.5 rounded-lg px-2.5 text-sm transition-colors outline-none focus-visible:ring-2 active:scale-[0.98]',
              active
                ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                : 'text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground',
            )}
          >
            <Icon className={cn('size-4', active && 'text-brand')} weight={active ? 'fill' : 'regular'} />
            {item.label}
          </Link>
        )
      })}
    </nav>
  )
}
