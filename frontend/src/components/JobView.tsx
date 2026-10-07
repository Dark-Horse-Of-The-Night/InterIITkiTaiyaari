import type { Job } from '../types'
import { useJobPolling } from '../useJobPolling'
import ErrorMessage from './ErrorMessage'
import ProgressSteps from './ProgressSteps'
import Results from './Results'

interface Props {
  initialJob: Job
  onReset: () => void
}

/** One processing job: live progress, then the results or the error. */
export default function JobView({ initialJob, onReset }: Props) {
  const { job, pollError } = useJobPolling(initialJob)
  const error = pollError ?? job.error

  if (job.status === 'done' && job.result && !pollError) {
    const totalSeconds = Object.values(job.result.timings_seconds).reduce((sum, s) => sum + s, 0)
    return (
      <div className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100">
          <p>
            ✓ Processed <span className="font-medium">{job.filename}</span> in {totalSeconds.toFixed(1)}s
          </p>
          <button
            type="button"
            onClick={onReset}
            className="font-medium text-emerald-800 underline hover:no-underline dark:text-emerald-200"
          >
            Process another recording
          </button>
        </div>
        <Results result={job.result} filename={job.filename} />
      </div>
    )
  }

  const finished = job.status === 'done' || job.status === 'failed'
  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-600 dark:text-slate-300">
        Processing <span className="font-medium text-slate-900 dark:text-white">{job.filename}</span>
      </p>
      <ProgressSteps stages={job.stages} active={!finished && !pollError} />
      {error && <ErrorMessage error={error} onRetry={onReset} />}
    </div>
  )
}
