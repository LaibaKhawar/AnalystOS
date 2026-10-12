import { CaretUpDownIcon, SignOutIcon } from '@phosphor-icons/react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useAuth } from '@/providers/auth-context'

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('')
}

export function UserMenu() {
  const { user, logout } = useAuth()
  const name = user?.name ?? 'Account'
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="hover:bg-sidebar-accent/60 focus-visible:ring-ring/60 flex w-full items-center gap-2.5 rounded-lg p-1.5 text-left outline-none focus-visible:ring-2"
        aria-label="Account menu"
      >
        <span className="bg-brand-soft text-brand-text flex size-7 shrink-0 items-center justify-center rounded-md text-xs font-semibold">
          {initials(name) || 'A'}
        </span>
        <span className="min-w-0 flex-1">
          <span className="text-foreground block truncate text-sm font-medium">{name}</span>
          <span className="text-muted-foreground block truncate text-xs">{user?.email ?? ''}</span>
        </span>
        <CaretUpDownIcon className="text-muted-foreground size-4" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-56">
        <DropdownMenuLabel className="truncate">{user?.email}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={logout}>
          <SignOutIcon />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
