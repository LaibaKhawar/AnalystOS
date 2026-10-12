import { WarningCircleIcon } from '@phosphor-icons/react'

export function FormError({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <div
      role="alert"
      className="border-danger/30 bg-danger-soft text-foreground flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm"
    >
      <WarningCircleIcon className="text-danger mt-0.5 size-4 shrink-0" weight="fill" />
      <span>{message}</span>
    </div>
  )
}
