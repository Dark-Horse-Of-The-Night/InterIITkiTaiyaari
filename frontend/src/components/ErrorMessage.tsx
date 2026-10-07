import type { JobError } from '../types'
import { AlertIcon } from './Icons'

interface Props {
  error: JobError
  onRetry: () => void
}

/** Shows which stage failed, what happened, and what to do. */
export default function ErrorMessage({ error, onRetry }: Props) {
  return (
    <div role="alert" className="pop-in flex gap-3.5 rounded-3xl border-2 border-danger-line bg-danger-soft px-6 py-5 text-left">
      <AlertIcon size={22} className="mt-0.5 shrink-0 text-danger-ink" />
      <div className="min-w-0">
        {error.stage && <p className="text-xs font-bold tracking-[0.06em] text-danger-ink uppercase">Stage: {error.stage}</p>}
        <p className="mt-1.5 text-[17px] font-semibold text-danger-ink">{error.message}</p>
        {error.fix && <p className="mt-1.5 text-[15px] text-danger-ink">What to do: {error.fix}</p>}
        <button type="button" onClick={onRetry} className="btn-outline focus-ring mt-4 border-danger-line">
          Try another file
        </button>
      </div>
    </div>
  )
}
