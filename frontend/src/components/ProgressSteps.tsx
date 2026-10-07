import { useEffect, useState } from 'react'

import type { StageProgress, StageState } from '../types'

// Friendlier names for the backend's stage names.
const LABELS: Record<string, string> = {
  'Speech-to-text': 'Transcribing the audio',
  Refiner: 'Refining technical terms',
  Documenter: 'Writing the meeting record',
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
      <ol className="space-y-3">
        {stages.map((stage) => (
          <li
            key={stage.name}
            data-state={stage.state}
            className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-900"
          >
            <StateIcon state={stage.state} />
            <div className="flex-1">
              <span className={`text-sm ${stage.state === 'pending' ? 'text-slate-400 dark:text-slate-500' : 'font-medium text-slate-800 dark:text-slate-100'}`}>
                {LABELS[stage.name] ?? stage.name}
              </span>
              {stage.state === 'running' && <StageHint stage={stage} />}
            </div>
            <span className="text-xs text-slate-500 dark:text-slate-400">{describe(stage)}</span>
          </li>
        ))}
      </ol>
      {active && (
        <p className="mt-4 text-center text-xs text-slate-500 dark:text-slate-400">
          {formatElapsed(elapsed)} elapsed · long recordings can take several minutes
        </p>
      )}
    </div>
  )
}

/** Where a long step has got to ("Part 2 of 6"), plus a retry note or a reassurance if it goes quiet. */
function StageHint({ stage }: { stage: StageProgress }) {
  const quiet = (stage.seconds_since_update ?? 0) > SLOW_STAGE_SECONDS
  const warning = stage.note ?? (quiet ? 'Taking longer than usual. The AI service may be busy.' : null)
  return (
    <>
      {stage.detail && <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{stage.detail}</p>}
      {warning && <p className="mt-0.5 text-xs text-amber-700 dark:text-amber-300">{warning}</p>}
    </>
  )
}

function describe(stage: StageProgress): string {
  switch (stage.state) {
    case 'pending':
      return 'Waiting'
    case 'running':
      return 'Running…'
    case 'done':
      return stage.seconds !== null ? `Done in ${stage.seconds}s` : 'Done'
    case 'failed':
      return 'Failed'
  }
}

function StateIcon({ state }: { state: StageState }) {
  const base = 'flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-bold'
  switch (state) {
    case 'pending':
      return <span aria-hidden className={`${base} border-2 border-slate-300 dark:border-slate-600`} />
    case 'running':
      return <span aria-hidden className={`${base} animate-spin border-2 border-indigo-200 border-t-indigo-600 dark:border-indigo-900 dark:border-t-indigo-400`} />
    case 'done':
      return <span aria-hidden className={`${base} bg-emerald-600 text-white`}>✓</span>
    case 'failed':
      return <span aria-hidden className={`${base} bg-red-600 text-white`}>✕</span>
  }
}

function formatElapsed(seconds: number): string {
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`
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
