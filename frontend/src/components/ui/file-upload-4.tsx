/**
 * Upload dropzone (Watermelon UI `file-upload-4`), customized for AnalystOS:
 * - the simulated progress timer is removed; progress comes from real XHR upload events
 * - an explicit "processing" phase while the server ingests and profiles the file
 * - validation and server errors render inline under each file, with retry
 * - Phosphor icons, theme tokens, 8px radius, keyboard-accessible drop target
 */
import { ArrowClockwiseIcon, FileCsvIcon, FileXlsIcon, UploadSimpleIcon, XIcon } from '@phosphor-icons/react'
import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { formatBytes, formatPercent } from '@/lib/format'
import { cn } from '@/lib/utils'

export type UploadItemStatus = 'uploading' | 'processing' | 'completed' | 'error'

export interface UploadItem {
  id: string
  name: string
  size: number
  progress: number
  status: UploadItemStatus
  error?: string
}

export interface UploadDropzoneProps {
  items: UploadItem[]
  onFiles: (files: File[]) => void
  onRemove: (id: string) => void
  onRetry?: (id: string) => void
  accept?: string[]
  maxSizeLabel?: string
  disabled?: boolean
  className?: string
}

function FileIcon({ name }: { name: string }) {
  return name.toLowerCase().endsWith('.xlsx') ? (
    <FileXlsIcon className="text-muted-foreground size-6" />
  ) : (
    <FileCsvIcon className="text-muted-foreground size-6" />
  )
}

function statusText(item: UploadItem): string {
  switch (item.status) {
    case 'uploading':
      return `Uploading ${formatPercent(item.progress, 0)}`
    case 'processing':
      return 'Profiling columns and types'
    case 'completed':
      return 'Ready'
    default:
      return 'Failed'
  }
}

export function UploadDropzone({
  items,
  onFiles,
  onRemove,
  onRetry,
  accept = ['csv', 'xlsx'],
  maxSizeLabel = '200 MB',
  disabled = false,
  className,
}: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const acceptAttr = accept.map((ext) => `.${ext}`).join(',')

  return (
    <div className={cn('grid grid-cols-1 gap-5 lg:grid-cols-[1.1fr_1fr]', className)}>
      <div className="flex flex-col gap-2">
        <button
          type="button"
          disabled={disabled}
          onClick={() => inputRef.current?.click()}
          onDragEnter={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragOver={(e) => e.preventDefault()}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            if (!disabled && e.dataTransfer.files.length) onFiles(Array.from(e.dataTransfer.files))
          }}
          aria-describedby="upload-help"
          className={cn(
            'bg-muted/30 flex min-h-52 w-full flex-col items-center justify-center gap-3 rounded-lg border border-dashed px-6 py-8 text-center transition-colors outline-none',
            'focus-visible:ring-ring/60 focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-60',
            dragging ? 'border-brand bg-brand-soft' : 'hover:border-brand/60',
          )}
        >
          <span className="bg-background flex size-10 items-center justify-center rounded-lg border">
            <UploadSimpleIcon className="text-brand size-5" />
          </span>
          <span className="text-foreground text-sm font-medium">Drop a CSV or Excel file here</span>
          <span className="text-muted-foreground text-xs">or</span>
          <span className="bg-background text-foreground inline-flex h-8 items-center rounded-lg border px-3 text-sm font-medium">
            Choose file
          </span>
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={acceptAttr}
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
          data-testid="upload-input"
          onChange={(e) => {
            if (e.target.files?.length) onFiles(Array.from(e.target.files))
            e.target.value = ''
          }}
        />
        <p id="upload-help" className="text-muted-foreground text-xs">
          Accepted: {accept.map((a) => `.${a}`).join(', ')}. Up to {maxSizeLabel}. Each sheet becomes a table.
        </p>
      </div>

      <div className="min-w-0">
        <p className="text-foreground mb-2 text-sm font-medium">Uploads</p>
        {items.length === 0 ? (
          <div className="flex min-h-40 flex-col items-center justify-center rounded-lg border border-dashed px-4 text-center">
            <p className="text-foreground text-sm">No uploads in this session</p>
            <p className="text-muted-foreground mt-1 max-w-64 text-xs">
              Files you add appear here with live progress, then open in the dataset explorer.
            </p>
          </div>
        ) : (
          <ul className="flex flex-col gap-3" aria-live="polite">
            {items.map((item) => (
              <li key={item.id} className="bg-card grid grid-cols-[auto_1fr_auto] gap-3 rounded-lg border p-3">
                <FileIcon name={item.name} />
                <div className="min-w-0">
                  <div className="flex items-baseline gap-2 text-sm">
                    <span className="text-foreground truncate font-medium">{item.name}</span>
                    <span className="tabular text-muted-foreground shrink-0 text-xs">{formatBytes(item.size)}</span>
                  </div>
                  <Progress
                    value={item.status === 'error' ? 100 : item.progress * 100}
                    aria-label={`${item.name} upload progress`}
                    className={cn(
                      'mt-2 h-1',
                      item.status === 'error' && '[&_[data-slot=progress-indicator]]:bg-danger',
                      item.status !== 'error' && '[&_[data-slot=progress-indicator]]:bg-brand',
                      item.status === 'processing' && 'motion-safe:animate-pulse',
                    )}
                  />
                  <p
                    className={cn('mt-1.5 text-xs', item.status === 'error' ? 'text-danger' : 'text-muted-foreground')}
                    role={item.status === 'error' ? 'alert' : undefined}
                  >
                    {item.status === 'error' ? (item.error ?? 'Upload failed') : statusText(item)}
                  </p>
                </div>
                <div className="flex items-start gap-1">
                  {item.status === 'error' && onRetry && (
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      onClick={() => onRetry(item.id)}
                      aria-label={`Retry ${item.name}`}
                    >
                      <ArrowClockwiseIcon />
                    </Button>
                  )}
                  {item.status !== 'uploading' && item.status !== 'processing' && (
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      onClick={() => onRemove(item.id)}
                      aria-label={`Dismiss ${item.name}`}
                    >
                      <XIcon />
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
