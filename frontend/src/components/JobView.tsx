import type { Job } from '../types'
import { useJobPolling } from '../useJobPolling'
import ErrorMessage from './ErrorMessage'
import ProgressSteps from './ProgressSteps'

interface Props {
  initialJob: Job
  onReset: () => void
}

/** One processing job: live progress, then the result or the error. */
export default function JobView({ initialJob, onReset }: Props) {
  const { job, pollError } = useJobPolling(initialJob)
  const finished = job.status === 'done' || job.status === 'failed'
  const error = pollError ?? job.error

  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-600 dark:text-slate-300">
        Processing <span className="font-medium text-slate-900 dark:text-white">{job.filename}</span>
      </p>
      <ProgressSteps stages={job.stages} active={!finished && !pollError} />

      {error && <ErrorMessage error={error} onRetry={onReset} />}

      {job.status === 'done' && job.result && !pollError && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5 text-sm text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100">
          <p className="font-medium">Done! The meeting record is ready.</p>
          <p className="mt-1">
            {job.result.record.decisions.length} decisions · {job.result.record.action_items.length} action items ·{' '}
            {job.result.record.open_items.length} open items
          </p>
          <button
            type="button"
            onClick={onReset}
            className="mt-3 text-sm font-medium text-emerald-800 underline hover:no-underline dark:text-emerald-200"
          >
            Process another recording
          </button>
        </div>
      )}
    </div>
  )
}
