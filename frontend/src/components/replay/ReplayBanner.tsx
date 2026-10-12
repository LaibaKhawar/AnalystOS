import { GithubLogoIcon } from '@phosphor-icons/react'
import type { ReplayInfo } from '@/api/replay'
import { formatDateTime } from '@/lib/format'

/** Shown on the static demo: says the page replays recorded analyses and cannot run new ones. */
export function ReplayBanner({ info }: { info: ReplayInfo }) {
  return (
    <div
      role="note"
      data-testid="replay-banner"
      className="bg-background/95 text-muted-foreground fixed bottom-3 left-1/2 z-50 flex w-[min(44rem,calc(100vw-2rem))] -translate-x-1/2 flex-wrap items-center justify-center gap-x-2 gap-y-1 rounded-xl border px-3 py-2 text-center text-xs shadow-lg backdrop-blur"
    >
      <span>
        <span className="text-foreground font-medium">Read-only replay.</span> Real analyses recorded{' '}
        {formatDateTime(info.recordedAt)} with {info.model}; asking new questions needs the backend.
      </span>
      <a
        href="https://github.com/LaibaKhawar/AnalystOS#quick-start-docker"
        className="text-brand-text inline-flex items-center gap-1 font-medium hover:underline"
      >
        <GithubLogoIcon className="size-3.5" /> Run it yourself
      </a>
    </div>
  )
}
