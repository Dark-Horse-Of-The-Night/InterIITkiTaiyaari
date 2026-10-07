import type { JobError } from '../types'

interface Props {
  error: JobError
  onRetry: () => void
}

/** Shows which stage failed, what happened, and what to do. */
export default function ErrorMessage({ error, onRetry }: Props) {
  return (
    <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-5 dark:border-red-900 dark:bg-red-950/40">
      {error.stage && (
        <p className="text-xs font-semibold tracking-wide text-red-700 uppercase dark:text-red-300">
          Stage: {error.stage}
        </p>
      )}
      <p className="mt-1 text-sm font-medium text-red-900 dark:text-red-100">{error.message}</p>
      {error.fix && <p className="mt-2 text-sm text-red-800 dark:text-red-200">What to do: {error.fix}</p>}
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 rounded-lg bg-white px-4 py-2 text-sm font-medium text-red-800 shadow-sm ring-1 ring-red-200 hover:bg-red-100 dark:bg-red-900/40 dark:text-red-100 dark:ring-red-800 dark:hover:bg-red-900/70"
      >
        Try another file
      </button>
    </div>
  )
}
