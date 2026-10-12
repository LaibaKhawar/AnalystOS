import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { Logo } from '@/components/brand/Logo'
import { ThemeToggle } from './ThemeToggle'

export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string
  subtitle: string
  children: ReactNode
  footer: ReactNode
}) {
  return (
    <div className="bg-background flex min-h-dvh flex-col">
      <header className="flex items-center justify-between px-4 py-4 sm:px-8">
        <Link
          to="/welcome"
          aria-label="AnalystOS home"
          className="focus-visible:ring-ring/60 rounded-lg outline-none focus-visible:ring-2"
        >
          <Logo />
        </Link>
        <ThemeToggle />
      </header>
      <main className="flex flex-1 items-start justify-center px-4 pt-[8vh] pb-16">
        <div className="w-full max-w-sm">
          <h1 className="text-foreground text-2xl font-semibold tracking-[-0.02em]">{title}</h1>
          <p className="text-muted-foreground mt-1.5 text-sm">{subtitle}</p>
          <div className="mt-8">{children}</div>
          <div className="text-muted-foreground mt-6 text-sm">{footer}</div>
        </div>
      </main>
    </div>
  )
}
