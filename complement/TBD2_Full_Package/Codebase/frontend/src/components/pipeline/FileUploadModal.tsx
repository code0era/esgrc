import { useState, useRef, useCallback } from 'react'
import { X, Upload, CheckCircle2, AlertCircle, File, Loader2, CloudUpload } from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'
import api from '@/lib/axios'
import { cn } from '@/lib/utils'
import { queryClient } from '@/lib/queryClient'

interface FileUploadModalProps {
  pipelineId:    string
  requiredFiles: string[]
  uploadedFiles: string[]
  onClose:       () => void
  onAllUploaded: () => void
}

interface UploadState {
  status:   'idle' | 'uploading' | 'done' | 'error'
  progress: number
  error:    string | null
}

// Human-readable descriptions for the data files an analyst uploads. Matched by
// basename; unknown files just show their name with no subtitle.
const FILE_LABELS: Record<string, string> = {
  'input_metric_values_esgrc.csv': 'Metric values - the ESG data to analyse (CSV)',
}
const labelFor = (name: string) => FILE_LABELS[name] ?? ''

export function FileUploadModal({
  pipelineId, requiredFiles, uploadedFiles, onClose, onAllUploaded,
}: FileUploadModalProps) {
  const [states, setStates]   = useState<Record<string, UploadState>>({})
  const [dragging, setDragging] = useState(false)
  const fileInputRef            = useRef<HTMLInputElement>(null)

  const setFileState = (name: string, state: Partial<UploadState>) =>
    setStates((prev) => ({ ...prev, [name]: { ...prev[name], ...state } as UploadState }))

  const uploadFile = useCallback(async (file: File) => {
    const expectedName = requiredFiles.find(
      (r) => r.toLowerCase() === file.name.toLowerCase() ||
             file.name.toLowerCase().includes(r.toLowerCase().split('.')[0])
    ) ?? file.name

    setFileState(expectedName, { status:'uploading', progress:0, error:null })

    try {
      await api.post(
        `/pipelines/${pipelineId}/upload-input?filename=${encodeURIComponent(expectedName)}`,
        file,
        {
          headers: { 'Content-Type': file.type || 'application/octet-stream' },
          // Override the shared client's 30s default: that budget is sized for
          // JSON API calls, not multi-hundred-MB data files, and was killing
          // large uploads partway through with a hard timeout error. Progress
          // is already tracked via onUploadProgress, so let the transfer run
          // as long as it needs instead of racing a fixed clock.
          timeout: 0,
          onUploadProgress: (e) => {
            // `e.total` is a genuine 0 (not undefined) for a 0-byte file, and
            // `??` only falls back on null/undefined - so `e.total ?? 1` stayed
            // 0, giving 0/0 = NaN and an invalid `NaN%` progress-bar width.
            // `||` falls back on 0 too, which is exactly what's needed here.
            const pct = Math.round(((e.loaded ?? 0) / (e.total || 1)) * 100)
            setFileState(expectedName, { progress: pct })
          },
        },
      )
      setFileState(expectedName, { status:'done', progress:100 })
      queryClient.invalidateQueries({ queryKey: ['input-files', pipelineId] })
    } catch (err: any) {
      setFileState(expectedName, { status:'error', error: err?.response?.data?.detail ?? 'Upload failed' })
    }
  }, [pipelineId, requiredFiles])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    Array.from(e.dataTransfer.files).forEach(uploadFile)
  }, [uploadFile])

  const allDone = requiredFiles.every(
    (f) => uploadedFiles.includes(f) || states[f]?.status === 'done'
  )

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 animate-fade-in" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2
                     w-full max-w-xl bg-bg-surface border border-border-default
                     rounded-2xl shadow-card-hover z-50 p-6 animate-slide-up"
          aria-describedby="upload-modal-desc"
        >
          <div className="flex items-center justify-between mb-5">
            <Dialog.Title className="text-lg font-bold text-text-primary">Upload Input Files</Dialog.Title>
            <Dialog.Close asChild>
              <button className="btn-icon" aria-label="Close upload modal"><X size={18} /></button>
            </Dialog.Close>
          </div>

          <Dialog.Description id="upload-modal-desc" className="text-sm text-text-secondary mb-5">
            Upload required input files for this pipeline run. Files are stored securely in cloud storage.
          </Dialog.Description>

          {/* Drop zone */}
          <div
            className={cn(
              'border-2 border-dashed rounded-xl p-8 text-center mb-5 transition-all cursor-pointer',
              dragging
                ? 'border-accent-primary bg-accent-primary/10'
                : 'border-border-default hover:border-accent-primary/50 hover:bg-bg-elevated'
            )}
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInputRef.current?.click() } }}
            role="button"
            tabIndex={0}
            aria-label="Drop files here or click to browse"
          >
            <CloudUpload size={36} className="mx-auto mb-3 text-text-muted" />
            <div className="text-sm font-medium text-text-primary mb-1">Drop files here</div>
            <div className="text-xs text-text-muted">or click to browse your computer</div>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => Array.from(e.target.files ?? []).forEach(uploadFile)}
              aria-label="File picker"
            />
          </div>

          {/* File list */}
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {requiredFiles.map((name) => {
              const isUploaded = uploadedFiles.includes(name)
              const state      = states[name]
              const status     = isUploaded ? 'done' : (state?.status ?? 'idle')

              return (
                <div
                  key={name}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-bg-elevated border border-border-subtle"
                >
                  <File size={14} className="text-text-muted flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-text-primary truncate flex items-center gap-1">
                      {name}
                      <span className="text-accent-danger text-xs">*</span>
                    </div>
                    {labelFor(name) && (
                      <div className="text-xs text-text-muted truncate">{labelFor(name)}</div>
                    )}
                    {status === 'uploading' && (
                      <div className="mt-1 h-1 bg-bg-surface rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-primary transition-all"
                          style={{ width: `${state?.progress ?? 0}%` }}
                        />
                      </div>
                    )}
                    {status === 'error' && (
                      <div className="text-xs text-accent-danger">{state?.error}</div>
                    )}
                  </div>
                  <div className="flex-shrink-0">
                    {status === 'done'      && <CheckCircle2 size={16} className="text-accent-success" />}
                    {status === 'uploading' && <Loader2 size={16} className="text-accent-primary animate-spin" />}
                    {status === 'error'     && <AlertCircle size={16} className="text-accent-danger" />}
                    {status === 'idle'      && <div className="w-4 h-4 rounded-full border border-border-default" />}
                  </div>
                </div>
              )
            })}
          </div>

          <div className="flex justify-end gap-3 mt-5 pt-4 border-t border-border-subtle">
            <button className="btn-secondary" onClick={onClose}>Cancel</button>
            <button
              className="btn-primary"
              disabled={!allDone}
              onClick={() => { onClose(); onAllUploaded() }}
            >
              <Upload size={15} />
              {allDone ? 'Files Ready' : 'Upload Required Files First'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
