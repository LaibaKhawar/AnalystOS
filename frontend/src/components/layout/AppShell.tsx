import { ListIcon, MagnifyingGlassIcon } from '@phosphor-icons/react'
import { useState } from 'react'
import { Link, Outlet, useLocation } from 'react-router'
import { Logo } from '@/components/brand/Logo'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { cn } from '@/lib/utils'
import { CommandPalette } from './CommandPalette'
import { SidebarNav } from './SidebarNav'
import { ThemeToggle } from './ThemeToggle'
import { UserMenu } from './UserMenu'

function SearchButton({ onClick, className }: { onClick: () => void; className?: string }) {
  const mac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'bg-background text-muted-foreground hover:text-foreground focus-visible:ring-ring/60 flex h-8 w-full items-center gap-2 rounded-lg border px-2.5 text-sm outline-none focus-visible:ring-2 active:scale-[0.98]',
        className,
      )}
    >
      <MagnifyingGlassIcon className="size-4" />
      <span className="flex-1 text-left">Jump to</span>
      <kbd className="bg-muted rounded-sm border px-1.5 font-mono text-[10px]">{mac ? 'Cmd K' : 'Ctrl K'}</kbd>
    </button>
  )
}

export function AppShell() {
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const { pathname } = useLocation()
  const fullBleed = pathname.startsWith('/workspace')

  return (
    <div className="bg-background flex min-h-dvh">
      <a
        href="#main"
        className="focus:bg-background focus:ring-ring sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:px-3 focus:py-2 focus:ring-2"
      >
        Skip to content
      </a>
      <aside className="bg-sidebar sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r px-3 py-4 lg:flex">
        <div className="flex items-center justify-between px-1.5">
          <Link
            to="/"
            aria-label="AnalystOS dashboard"
            className="focus-visible:ring-ring/60 rounded-lg outline-none focus-visible:ring-2"
          >
            <Logo />
          </Link>
          <ThemeToggle />
        </div>
        <SearchButton onClick={() => setPaletteOpen(true)} className="mt-5" />
        <div className="mt-4 flex-1 overflow-y-auto">
          <SidebarNav />
        </div>
        <UserMenu />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="bg-background/95 sticky top-0 z-30 flex h-12 items-center gap-2 border-b px-3 backdrop-blur lg:hidden">
          <Button variant="ghost" size="icon" aria-label="Open navigation" onClick={() => setMobileOpen(true)}>
            <ListIcon className="size-5" />
          </Button>
          <Link to="/" aria-label="AnalystOS dashboard">
            <Logo />
          </Link>
          <div className="ml-auto flex items-center gap-1">
            <Button variant="ghost" size="icon" aria-label="Search" onClick={() => setPaletteOpen(true)}>
              <MagnifyingGlassIcon className="size-4" />
            </Button>
            <ThemeToggle />
          </div>
        </header>
        <main
          id="main"
          className={cn(
            'min-w-0 flex-1',
            fullBleed ? '' : 'mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8',
          )}
        >
          <Outlet />
        </main>
      </div>

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="bg-sidebar w-72 p-0">
          <SheetHeader className="border-b px-4 py-3">
            <SheetTitle>
              <Logo />
            </SheetTitle>
            <SheetDescription className="sr-only">Main navigation</SheetDescription>
          </SheetHeader>
          <div className="flex flex-1 flex-col gap-4 px-3 py-2">
            <SidebarNav onNavigate={() => setMobileOpen(false)} />
          </div>
          <div className="border-t p-3">
            <UserMenu />
          </div>
        </SheetContent>
      </Sheet>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  )
}
