import { useState } from 'react'

import { ApiError, SERVER_UNREACHABLE, uploadMeeting } from './api'
import ErrorMessage from './components/ErrorMessage'
import JobView from './components/JobView'
import UploadForm from './components/UploadForm'
import type { Job, JobError } from './types'

export default function App() {
  const [job, setJob] = useState<Job | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<JobError | null>(null)

  async function handleUpload(file: File, glossary: string) {
    setUploading(true)
    setUploadError(null)
    try {
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
    <div className="min-h-screen bg-slate-100 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto max-w-3xl px-4 py-5">
          <h1 className="text-xl font-semibold">AI Meeting Assistant</h1>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            Upload an English meeting recording to get a transcript, a refined transcript and a structured meeting record.
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-8">
        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
          {job ? (
            // key: a new job gets a fresh view (and fresh polling)
            <JobView key={job.job_id} initialJob={job} onReset={reset} />
          ) : uploadError ? (
            <ErrorMessage error={uploadError} onRetry={reset} />
          ) : (
            <UploadForm onSubmit={handleUpload} uploading={uploading} />
          )}
        </section>
      </main>
    </div>
  )
}
