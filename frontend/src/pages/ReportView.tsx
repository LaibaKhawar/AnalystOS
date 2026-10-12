import { ArrowLeftIcon, DownloadSimpleIcon, FileHtmlIcon, FilePdfIcon, FileXlsIcon } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { downloadFile, errorMessage } from '@/api/client'
import { reportsApi } from '@/api/endpoints'
import { PageHeader } from '@/components/common/PageHeader'
import { ErrorState } from '@/components/common/States'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useAnalysis } from '@/hooks/queries/analyses'
import { useReport, useReportHtml } from '@/hooks/queries/reports'
import { formatDateTime, noDashes } from '@/lib/format'

type Kind = 'html' | 'pdf' | 'xlsx'

export default function ReportView() {
  const { reportId = '' } = useParams()
  const report = useReport(reportId)
  const html = useReportHtml(reportId)
  const analysis = useAnalysis(report.data?.analysis_id)
  const [pending, setPending] = useState<Kind | null>(null)
  const [errors, setErrors] = useState<Partial<Record<Kind, string>>>({})

  useEffect(() => {
    const url = html.data
    return () => {
      if (url) URL.revokeObjectURL(url)
    }
  }, [html.data])

  const download = async (kind: Kind) => {
    setPending(kind)
    setErrors((e) => ({ ...e, [kind]: undefined }))
    try {
      if (kind === 'html') await downloadFile(reportsApi.htmlPath(reportId), `${reportId}.html`, { download: true })
      if (kind === 'pdf') await downloadFile(reportsApi.pdfPath(reportId), `${reportId}.pdf`)
      if (kind === 'xlsx') await downloadFile(reportsApi.xlsxPath(reportId), `${reportId}-results.xlsx`)
    } catch (error) {
      setErrors((e) => ({ ...e, [kind]: errorMessage(error) }))
    } finally {
      setPending(null)
    }
  }

  if (report.isError)
    return <ErrorState error={report.error} title="Could not open this report" onRetry={() => void report.refetch()} />

  const exportError = errors.html ?? errors.pdf ?? errors.xlsx
  const a = analysis.data
  return (
    <div className="flex flex-col gap-5">
      <Link
        to="/reports"
        className="text-muted-foreground hover:text-foreground inline-flex w-fit items-center gap-1.5 text-xs"
      >
        <ArrowLeftIcon className="size-3.5" /> All reports
      </Link>
      <PageHeader
        title={report.data ? noDashes(report.data.title) : <Skeleton className="h-7 w-80 max-w-full" />}
        description={
          report.data
            ? `Generated ${formatDateTime(report.data.created_at)}${report.data.content.dataset?.name ? ` from ${report.data.content.dataset.name}` : ''}`
            : undefined
        }
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void download('html')}
              disabled={pending !== null}
              data-testid="download-html"
            >
              <FileHtmlIcon data-icon="inline-start" />
              {pending === 'html' ? 'Preparing' : 'HTML'}
            </Button>
            <Button variant="outline" size="sm" onClick={() => void download('pdf')} disabled={pending !== null}>
              <FilePdfIcon data-icon="inline-start" />
              {pending === 'pdf' ? 'Preparing' : 'PDF'}
            </Button>
            <Button variant="outline" size="sm" onClick={() => void download('xlsx')} disabled={pending !== null}>
              <FileXlsIcon data-icon="inline-start" />
              {pending === 'xlsx' ? 'Preparing' : 'Results Excel'}
            </Button>
          </>
        }
      />
      {exportError && (
        <div
          role="alert"
          className="border-warning/30 bg-warning-soft text-foreground flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm"
        >
          <DownloadSimpleIcon className="text-warning mt-0.5 size-4 shrink-0" />
          <span>
            {errors.pdf ? 'PDF export is not available on this server. ' : 'Export failed. '}
            {exportError} {errors.pdf && 'Download HTML and print it to PDF from your browser instead.'}
          </span>
        </div>
      )}
      {a && (
        <p className="text-muted-foreground text-xs">
          From the analysis{' '}
          <Link className="text-brand-text hover:underline" to={`/workspace/${a.conversation_id}?analysis=${a.id}`}>
            {noDashes(a.question)}
          </Link>
        </p>
      )}
      <div className="overflow-hidden rounded-lg border bg-white">
        {html.isPending && (
          <div className="bg-card flex flex-col gap-3 p-6" aria-busy="true">
            <Skeleton className="h-7 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-64" />
            <Skeleton className="h-40" />
          </div>
        )}
        {html.isError && (
          <ErrorState
            className="m-4"
            error={html.error}
            title="Could not render the report"
            onRetry={() => void html.refetch()}
          />
        )}
        {html.data && (
          <iframe
            title="Report preview"
            src={html.data}
            sandbox=""
            className="block h-[75vh] min-h-[480px] w-full"
            data-testid="report-frame"
          />
        )}
      </div>
    </div>
  )
}
