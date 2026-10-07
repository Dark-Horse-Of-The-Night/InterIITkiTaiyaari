import type { Job, PreviewCorrection } from '../types'
import { useJobPolling } from '../useJobPolling'
import { SoundBars } from './Brand'
import ErrorMessage from './ErrorMessage'
import ProgressSteps from './ProgressSteps'
import Results from './Results'

interface Props {
  initialJob: Job
  file?: File | null // the uploaded recording, for the audio player
  onReset: () => void
}

// What the page says while each stage runs.
const HEADLINES: Record<string, string> = {
  'Speech-to-text': 'Listening to the audio…',
  Refiner: 'Fixing the jargon…',
  Documenter: 'Writing your minutes…',
}

/** One processing job: live progress (with the fix-it moment), then the results or the error. */
export default function JobView({ initialJob, file = null, onReset }: Props) {
  const { job, pollError } = useJobPolling(initialJob)
  const error = pollError ?? job.error

  if (job.status === 'done' && job.result && !pollError) {
    return <Results result={job.result} filename={job.filename} file={file} />
  }

  const running = job.stages.find((s) => s.state === 'running')
  const headline = error ? 'That didn’t work' : running ? HEADLINES[running.name] ?? 'Working…' : 'Getting ready…'

  return (
    <div className="mx-auto max-w-[640px] pt-6 text-center">
      <SoundBars height={92} motion={error ? 'none' : 'bounce'} />
      <h1 className="display mt-6 text-[36px] leading-[1.05] sm:text-[44px]" aria-live="polite">
        {headline}
      </h1>
      <p className="mt-2 truncate font-mono text-sm text-muted">{job.filename}</p>

      <div className="mt-6">
        <ProgressSteps stages={job.stages} />
      </div>

      {error && (
        <div className="mt-8">
          <ErrorMessage error={error} onRetry={onReset} />
        </div>
      )}

      {!error && job.preview && job.preview.length > 0 && <FixItCard corrections={job.preview} />}
    </div>
  )
}

const SHOWN = 6

/** The "fix-it" moment: each misheard word is struck through and the right term pops in. */
function FixItCard({ corrections }: { corrections: PreviewCorrection[] }) {
  return (
    <section className="rise-in mt-10 rounded-3xl border-2 border-line bg-ground px-6 py-5 text-left shadow-[0_10px_30px_rgba(224,106,28,0.08)]">
      <h2 className="display text-[22px]">
        We fixed {corrections.length} misheard term{corrections.length === 1 ? '' : 's'}
      </h2>
      <p className="mb-4 text-[14.5px] text-muted">While you wait, here's what the speech recognition got wrong.</p>
      <ul className="flex flex-col gap-2.5">
        {corrections.slice(0, SHOWN).map((c, i) => (
          <li key={i} className="rise-in flex items-center gap-3 rounded-2xl bg-orange-soft px-3.5 py-2.5" style={{ animationDelay: `${i * 0.35}s` }}>
            <span className="strike-out font-mono text-[15px] text-muted" style={{ animationDelay: `${i * 0.35 + 0.3}s` }}>
              {c.before || '(nothing)'}
            </span>
            <span aria-hidden className="text-faint">→</span>
            <span className="pop-in font-mono text-[15px] font-semibold text-orange-ink" style={{ animationDelay: `${i * 0.35 + 0.6}s` }}>
              {c.after || '(removed)'}
            </span>
            <span className="ml-auto hidden max-w-[45%] truncate text-[13px] text-muted sm:block" title={c.sentence}>
              {c.sentence}
            </span>
          </li>
        ))}
      </ul>
      {corrections.length > SHOWN && (
        <p className="mt-3 text-sm text-muted">+ {corrections.length - SHOWN} more · Names, numbers and "not"s are never changed.</p>
      )}
      {corrections.length <= SHOWN && <p className="mt-3 text-sm text-muted">Names, numbers and "not"s are never changed.</p>}
    </section>
  )
}
