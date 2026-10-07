import { useState } from 'react'

import { ApiError, SERVER_UNREACHABLE, uploadMeeting } from './api'
import ErrorMessage from './components/ErrorMessage'
import { ChevronRightIcon, PlusIcon, WaveIcon } from './components/Icons'
import JobView from './components/JobView'
import UploadForm from './components/UploadForm'
import type { Job, JobError } from './types'

export default function App() {
  const [job, setJob] = useState<Job | null>(null)
  const [fileSize, setFileSize] = useState<number | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<JobError | null>(null)

  async function handleUpload(file: File, glossary: string) {
    setUploading(true)
    setUploadError(null)
    try {
      setFileSize(file.size)
      setJob(await uploadMeeting(file, glossary))
    } catch (error) {
      setUploadError(error instanceof ApiError ? error.error : SERVER_UNREACHABLE)
    } finally {
      setUploading(false)
    }
  }

  function reset() {
    setJob(null)
    setUploadError(null)
  }

  return (
    <div className="min-h-screen bg-ground text-ink">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-[1120px] flex-wrap items-center justify-between gap-4 px-6 py-3.5">
          <div className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-[9px] bg-accent text-on-accent">
              <WaveIcon size={18} strokeWidth={2.2} />
            </span>
            <span className="text-base font-semibold tracking-[-0.01em]">Meeting Assistant</span>
          </div>
          {job ? (
            <button type="button" onClick={reset} className="btn-secondary">
              <PlusIcon size={16} />
              New recording
            </button>
          ) : (
            <nav aria-label="Pipeline" className="flex flex-wrap items-center gap-2 text-[13px] text-muted">
              <span>Speech-to-text</span>
              <ChevronRightIcon size={14} className="text-faint" />
              <span>Refine terms</span>
              <ChevronRightIcon size={14} className="text-faint" />
              <span>Meeting record</span>
            </nav>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-[1120px] px-6 pt-10 pb-16">
        {job ? (
          // key: a new job gets a fresh view (and fresh polling)
          <JobView key={job.job_id} initialJob={job} fileSize={fileSize} onReset={reset} />
        ) : uploadError ? (
          <div className="mx-auto max-w-[720px]">
            <ErrorMessage error={uploadError} onRetry={reset} />
          </div>
        ) : (
          <UploadForm onSubmit={handleUpload} uploading={uploading} />
        )}
      </main>
    </div>
  )
}
