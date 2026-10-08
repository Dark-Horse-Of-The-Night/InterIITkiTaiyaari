import { useState } from 'react'

import { ApiError, SERVER_UNREACHABLE, uploadMeeting } from './api'
import { Logo, WaveBackground } from './components/Brand'
import ErrorMessage from './components/ErrorMessage'
import JobView from './components/JobView'
import UploadForm from './components/UploadForm'
import type { Job, JobError } from './types'

export default function App() {
  const [job, setJob] = useState<Job | null>(null)
  const [file, setFile] = useState<File | null>(null) // kept in the browser for the audio player
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<JobError | null>(null)

  async function handleUpload(chosen: File, glossary: string) {
    setUploading(true)
    setUploadError(null)
    try {
      setFile(chosen)
      setJob(await uploadMeeting(chosen, glossary))
    } catch (error) {
      setUploadError(error instanceof ApiError ? error.error : SERVER_UNREACHABLE)
    } finally {
      setUploading(false)
    }
  }

  function reset() {
    setJob(null)
    setFile(null)
    setUploadError(null)
    window.scrollTo?.({ top: 0 })
  }

  return (
    <div className="relative isolate min-h-screen text-ink">
      <WaveBackground />
      <header className="mx-auto flex max-w-[1040px] items-center justify-between gap-3 px-6 py-5">
        {/* The logo always leads back to the upload page, like "New recording". */}
        <button
          type="button"
          onClick={reset}
          disabled={uploading}
          aria-label="Meeting Assistant: back to the upload page"
          className="focus-ring cursor-pointer rounded-xl transition-transform hover:scale-[1.03] disabled:cursor-wait"
        >
          <Logo />
        </button>
        {(job || uploadError) && (
          <button type="button" onClick={reset} className="btn-outline focus-ring border-ink">
            + New recording
          </button>
        )}
      </header>

      <main className="mx-auto max-w-[1040px] px-6 pb-20">
        {job ? (
          // key: a new job gets a fresh view (and fresh polling)
          <JobView key={job.job_id} initialJob={job} file={file} onReset={reset} />
        ) : uploadError ? (
          <div className="mx-auto mt-10 max-w-[640px]">
            <ErrorMessage error={uploadError} onRetry={reset} />
          </div>
        ) : (
          <UploadForm onSubmit={handleUpload} uploading={uploading} />
        )}
      </main>
    </div>
  )
}
