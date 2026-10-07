import { formatSize } from '../fileChecks'
import type { Job } from '../types'
import { useJobPolling } from '../useJobPolling'
import ErrorMessage from './ErrorMessage'
import { AudioFileIcon } from './Icons'
import ProgressSteps from './ProgressSteps'
import Results from './Results'

interface Props {
  initialJob: Job
  fileSize?: number | null
  onReset: () => void
}

/** One processing job: live progress, then the results or the error. */
export default function JobView({ initialJob, fileSize = null, onReset }: Props) {
  const { job, pollError } = useJobPolling(initialJob)
  const error = pollError ?? job.error

  if (job.status === 'done' && job.result && !pollError) {
    return <Results result={job.result} filename={job.filename} />
  }

  const finished = job.status === 'done' || job.status === 'failed'
  return (
    <div className="mx-auto max-w-[760px]">
      <p className={`eyebrow mb-2.5 ${error ? 'text-danger-strong' : 'text-accent-ink'}`}>
        {error ? 'Something went wrong' : 'Processing'}
      </p>
      <h1 className="text-[30px] leading-[1.15] font-semibold tracking-[-0.02em] sm:text-[32px]">
        {error ? 'The meeting record could not be built' : 'Building your meeting record'}
      </h1>

      <div className="card mt-6 flex flex-wrap items-center gap-3 rounded-[14px] px-4 py-3.5">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-[10px] bg-subtle text-ink-2">
          <AudioFileIcon size={20} strokeWidth={1.8} />
        </span>
        <div className="min-w-40 flex-1">
          <p className="truncate font-medium">{job.filename}</p>
          {fileSize !== null && <p className="text-[13px] text-muted">{formatSize(fileSize)}</p>}
        </div>
      </div>

      <div className="mt-6">
        <ProgressSteps stages={job.stages} active={!finished && !pollError} />
      </div>
      {error && (
        <div className="mt-6">
          <ErrorMessage error={error} onRetry={onReset} />
        </div>
      )}
    </div>
  )
}
