import { useEffect, useState } from 'react'

import { formatSeconds } from '../format'
import type { StageProgress, StageState } from '../types'
import { CheckIcon, ClockIcon, CloseIcon, InfoIcon } from './Icons'

// Friendlier names for the backend's stage names.
const LABELS: Record<string, string> = {
  'Speech-to-text': 'Transcribing the audio',
  Refiner: 'Refining technical terms',
  Documenter: 'Writing the meeting record',
}

// What each step does, shown while it is waiting.
const DESCRIPTIONS: Record<string, string> = {
  'Speech-to-text': 'Long recordings are split at pauses in speech',
  Refiner: 'Fixes misheard terms; names, numbers and negations never change',
  Documenter: 'Long meetings are written in parts, then cross-checked',
}

// After this long without progress in a step, reassure the user that a slow AI service isn't a frozen app.
export const SLOW_STAGE_SECONDS = 20

interface Props {
  stages: StageProgress[]
  active: boolean // true while processing; drives the elapsed-time counter
}

export default function ProgressSteps({ stages, active }: Props) {
  const elapsed = useElapsedSeconds(active)

  return (
    <div>
      <ol className="card overflow-hidden">
        {stages.map((stage, i) => (
          <li
            key={stage.name}
            data-state={stage.state}
            className={`flex gap-4 p-5 ${i < stages.length - 1 ? 'border-b border-line-soft' : ''} ${
              stage.state === 'running' ? 'bg-surface-2' : ''
            }`}
          >
            <StateIcon state={stage.state} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap justify-between gap-x-3 gap-y-0.5">
                <span className={stage.state === 'pending' ? 'font-medium text-muted' : 'font-semibold'}>
                  {LABELS[stage.name] ?? stage.name}
                </span>
                <span className={`text-[13px] ${statusColour(stage.state)}`}>{describe(stage)}</span>
              </div>
              {stage.state === 'running' ? (
                <StageHint stage={stage} />
              ) : stage.state === 'pending' ? (
                <p className="mt-0.5 text-sm text-faint">{DESCRIPTIONS[stage.name]}</p>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
      {active && (
        <p className="mt-5 flex items-start gap-2 text-[13.5px] text-muted">
          <InfoIcon size={16} className="mt-0.5 shrink-0" />
          <span>
            <span className="font-mono">{formatElapsed(elapsed)}</span> elapsed · long recordings can take several
            minutes on the free tier. Keep this tab open; progress updates every second.
          </span>
        </p>
      )}
    </div>
  )
}

/** Where a long step has got to ("Part 2 of 6"), plus a retry note or a reassurance if it goes quiet. */
function StageHint({ stage }: { stage: StageProgress }) {
  const quiet = (stage.seconds_since_update ?? 0) > SLOW_STAGE_SECONDS
  const warning = stage.note ?? (quiet ? 'Taking longer than usual. The AI service may be busy.' : null)
  const fraction = progressFraction(stage.detail)
  return (
    <>
      {stage.detail && <p className="mt-0.5 text-sm text-muted">{stage.detail}</p>}
      {fraction !== null && (
        <div
          role="progressbar"
          aria-label={`${LABELS[stage.name] ?? stage.name} progress`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(fraction * 100)}
          className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-line"
        >
          <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${fraction * 100}%` }} />
        </div>
      )}
      {warning && (
        <p className="mt-3 flex items-start gap-2 rounded-[10px] bg-warn-soft px-3 py-2.5 text-[13.5px] text-warn-ink">
          <ClockIcon size={16} className="mt-0.5 shrink-0" />
          <span>{warning}</span>
        </p>
      )}
    </>
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
  switch (stage.state) {
    case 'pending':
      return 'Waiting'
    case 'running':
      return 'Running'
    case 'done':
      return stage.seconds !== null ? `Done in ${formatSeconds(stage.seconds)}` : 'Done'
    case 'failed':
      return 'Failed'
  }
}

function statusColour(state: StageState): string {
  if (state === 'running') return 'font-medium text-accent-ink'
  if (state === 'failed') return 'font-medium text-danger-strong'
  if (state === 'done') return 'font-mono text-ink-2'
  return 'text-muted'
}

function StateIcon({ state }: { state: StageState }) {
  const base = 'flex size-8 shrink-0 items-center justify-center rounded-full'
  switch (state) {
    case 'pending':
      return <span aria-hidden className={`${base} border-2 border-line-strong`} />
    case 'running':
      return <span aria-hidden className={`${base} animate-spin border-[2.5px] border-accent-soft border-t-accent`} />
    case 'done':
      return (
        <span aria-hidden className={`${base} bg-accent text-on-accent`}>
          <CheckIcon size={16} strokeWidth={2.6} />
        </span>
      )
    case 'failed':
      return (
        <span aria-hidden className={`${base} bg-danger-strong text-white`}>
          <CloseIcon size={15} strokeWidth={2.6} />
        </span>
      )
  }
}

function formatElapsed(seconds: number): string {
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s`
}

function useElapsedSeconds(active: boolean): number {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (!active) return
    const started = Date.now()
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => clearInterval(timer)
  }, [active])
  return elapsed
}
