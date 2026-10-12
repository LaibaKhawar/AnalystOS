import { TrashIcon } from '@phosphor-icons/react'
import { toast } from 'sonner'
import { errorMessage } from '@/api/client'
import type { DataSource } from '@/api/types'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { useDeleteSource } from '@/hooks/queries/sources'

export function DeleteSourceButton({ source, onDeleted }: { source: DataSource; onDeleted?: () => void }) {
  const remove = useDeleteSource()
  const isFile = source.kind === 'file'
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={`Delete ${source.name}`}>
          <TrashIcon />
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete {source.name}?</AlertDialogTitle>
          <AlertDialogDescription>
            {isFile
              ? 'The uploaded file, its profile and every conversation and analysis on it are removed. This cannot be undone.'
              : 'The saved connection, its encrypted credentials and every conversation and analysis on it are removed. Your database is not touched.'}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep it</AlertDialogCancel>
          <AlertDialogAction
            className="bg-danger hover:bg-danger/90 text-white"
            onClick={() =>
              remove.mutate(source.id, {
                onSuccess: () => {
                  toast(`${source.name} deleted`)
                  onDeleted?.()
                },
                onError: (e) => toast.error(errorMessage(e)),
              })
            }
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
