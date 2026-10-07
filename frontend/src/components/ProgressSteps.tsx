import type { StageProgress } from '../types'
import { CheckIcon, ClockIcon, CloseIcon } from './Icons'

// Short, friendly names for the backend's stages.
const LABELS: Record<string, string> = {
  'Speech-to-text': 'Listening',
  Refiner: 'Fixing jargon',
  Documenter: 'Writing minutes',
}

// After this long without progress in a step, reassure the user that a slow AI service isn't a frozen app.
export const SLOW_STAGE_SECONDS = 20

/** The three step pills, plus the running step's progress bar, detail and any retry note. */
export default function ProgressSteps({ stages }: { stages: StageProgress[] }) {
  const running = stages.find((s) => s.state === 'running')
  return (
    <div>
      <ol aria-label="Progress" className="flex flex-wrap justify-center gap-2">
        {stages.map((stage, i) => (
          <li
            key={stage.name}
            data-state={stage.state}
            className={`flex items-center gap-1.5 rounded-full py-1.5 pr-3.5 pl-1.5 text-sm font-semibold transition-colors ${
              stage.state === 'running'
                ? 'bg-orange text-ink'
                : stage.state === 'done'
                  ? 'bg-mint-soft text-mint-ink'
                  : stage.state === 'failed'
                    ? 'bg-danger-soft text-danger-ink'
                    : 'bg-stone-soft text-muted'
            }`}
          >
            <span
              className={`flex size-[22px] items-center justify-center rounded-full text-xs font-extrabold ${
                stage.state === 'done' ? 'pop-in bg-mint-ink text-white' : stage.state === 'failed' ? 'bg-danger-ink text-white' : 'bg-white text-ink'
              }`}
              aria-hidden
            >
              {stage.state === 'done' ? <CheckIcon size={12} strokeWidth={3.2} /> : stage.state === 'failed' ? <CloseIcon size={12} strokeWidth={3.2} /> : i + 1}
            </span>
            <span>{LABELS[stage.name] ?? stage.name}</span>
            <span className="sr-only">{describe(stage)}</span>
            {stage.state === 'done' && stage.seconds !== null && (
              <span className="font-mono text-xs font-medium opacity-75">{formatShort(stage.seconds)}</span>
            )}
          </li>
        ))}
      </ol>
      {running && <StageHint stage={running} />}
    </div>
  )
}

function StageHint({ stage }: { stage: StageProgress }) {
  const quiet = (stage.seconds_since_update ?? 0) > SLOW_STAGE_SECONDS
  const warning = stage.note ?? (quiet ? 'Taking longer than usual. The AI service may be busy.' : null)
  const fraction = progressFraction(stage.detail)
  return (
    <div className="mx-auto mt-5 max-w-[420px]">
      {fraction !== null && (
        <div
          role="progressbar"
          aria-label={`${LABELS[stage.name] ?? stage.name} progress`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(fraction * 100)}
          className="h-2.5 overflow-hidden rounded-full bg-orange-track"
        >
          <div className="h-full rounded-full bg-orange transition-[width] duration-700" style={{ width: `${fraction * 100}%` }} />
        </div>
      )}
      {stage.detail && <p className="mt-2 text-sm text-muted">{stage.detail}</p>}
      {warning && (
        <p className="pop-in mt-3 inline-flex items-start gap-2 rounded-2xl bg-sun-soft px-3.5 py-2 text-left text-sm text-sun-ink">
          <ClockIcon size={16} className="mt-0.5 shrink-0" />
          <span>{warning}</span>
        </p>
      )}
    </div>
  )
}

/** "Part 3 of 8" -> about 0.31 (halfway through part 3). */
function progressFraction(detail: string | null): number | null {
  const match = detail?.match(/(\d+) of (\d+)/)
  if (!match) return null
  const [current, total] = [Number(match[1]), Number(match[2])]
  return total > 0 ? Math.min(1, (current - 0.5) / total) : null
}

function describe(stage: StageProgress): string {
  if (stage.state === 'done') return stage.seconds !== null ? `Done in ${stage.seconds}s` : 'Done'
  return { pending: 'Waiting', running: 'Running', failed: 'Failed' }[stage.state]
}

function formatShort(seconds: number): string {
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m${String(Math.round(seconds % 60)).padStart(2, '0')}`
}
