import type { JobError } from '../types'
import { AlertIcon } from './Icons'

interface Props {
  error: JobError
  onRetry: () => void
}

/** Shows which stage failed, what happened, and what to do. */
export default function ErrorMessage({ error, onRetry }: Props) {
  return (
    <div role="alert" className="flex gap-3.5 rounded-[14px] border border-danger-line bg-danger-soft px-5 py-[18px]">
      <AlertIcon size={20} className="mt-0.5 shrink-0 text-danger-strong" />
      <div className="min-w-0">
        {error.stage && <p className="eyebrow text-xs text-danger-strong">Stage: {error.stage}</p>}
        <p className="mt-1.5 font-semibold text-danger-ink">{error.message}</p>
        {error.fix && <p className="mt-1.5 text-sm text-danger-ink">What to do: {error.fix}</p>}
        <button
          type="button"
          onClick={onRetry}
          className="mt-3.5 inline-flex min-h-10 cursor-pointer items-center rounded-[10px] border border-danger-line bg-surface px-3.5 text-sm font-medium text-danger-ink hover:bg-danger-soft"
        >
          Try another file
        </button>
      </div>
    </div>
  )
}
