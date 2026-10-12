export const MAX_UPLOAD_BYTES = 200 * 1024 * 1024
export const ACCEPTED_EXTENSIONS = ['csv', 'xlsx'] as const

export type UploadValidation = { ok: true } | { ok: false; message: string }

export function fileExtension(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot === -1 ? '' : name.slice(dot + 1).toLowerCase()
}

/** Client-side checks before sending a file to /api/sources/upload. */
export function validateUpload(file: Pick<File, 'name' | 'size'>): UploadValidation {
  const ext = fileExtension(file.name)
  if (!ext || !(ACCEPTED_EXTENSIONS as readonly string[]).includes(ext)) {
    return {
      ok: false,
      message: `${file.name} is not supported. Upload a .csv or .xlsx file.`,
    }
  }
  if (file.size === 0) {
    return { ok: false, message: `${file.name} is empty.` }
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    const mb = (file.size / (1024 * 1024)).toFixed(0)
    return { ok: false, message: `${file.name} is ${mb} MB. The limit is 200 MB.` }
  }
  return { ok: true }
}

/** Default dataset name from a file name: "q3_sales-2026.csv" -> "q3 sales 2026". */
export function defaultDatasetName(fileName: string): string {
  const base = fileName.replace(/\.[^.]+$/, '')
  return base.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()
}
