import type { ReactNode } from 'react'

import { formatTime } from '../format'
import type { Correction, Transcript } from '../types'

interface Props {
  transcript: Transcript
  corrections?: Correction[] // refined transcript only: highlight what the refiner changed
  warnings?: string[]
}

export default function TranscriptView({ transcript, corrections, warnings = [] }: Props) {
  return (
    <div className="space-y-4">
      {corrections && <CorrectionsSummary corrections={corrections} />}
      {warnings.length > 0 && (
        <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
          <p className="font-medium">Edits the safety checks rejected (original wording kept):</p>
          <ul className="mt-1 list-disc pl-5">
            {warnings.map((warning, i) => (
              <li key={i}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
      <ol className="space-y-1.5">
        {transcript.segments.map((segment, i) => (
          <li key={i} className="flex gap-3 text-sm leading-relaxed">
            <span className="shrink-0 pt-px font-mono text-xs text-slate-400 dark:text-slate-500">{formatTime(segment.start)}</span>
            <span className="text-slate-800 dark:text-slate-200">
              {corrections ? highlight(segment.text, corrections.filter((c) => c.segment_id === i)) : segment.text}
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}

function CorrectionsSummary({ corrections }: { corrections: Correction[] }) {
  if (corrections.length === 0) {
    return <p className="text-sm text-slate-500 dark:text-slate-400">The refiner found no technical terms to correct.</p>
  }
  return (
    <div className="rounded-lg bg-slate-50 p-3 dark:bg-slate-800/60">
      <p className="text-sm text-slate-700 dark:text-slate-300">
        {corrections.length} correction{corrections.length === 1 ? '' : 's'}. Highlighted words were corrected; hover to see
        what Whisper heard.
      </p>
      <ul className="mt-2 flex flex-wrap gap-2">
        {corrections.map((c, i) => (
          <li key={i} className="rounded bg-white px-2 py-0.5 text-xs text-slate-700 ring-1 ring-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-700">
            <s className="text-slate-400">{c.before || '(nothing)'}</s> → <span className="font-medium">{c.after || '(removed)'}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Wrap each corrected span in <mark>, searching left to right so repeated words line up. */
function highlight(text: string, corrections: Correction[]): ReactNode {
  const parts: ReactNode[] = []
  let cursor = 0
  corrections.forEach((correction, i) => {
    if (!correction.after) return // a pure deletion has nothing to highlight
    const index = text.indexOf(correction.after, cursor)
    if (index === -1) return
    parts.push(text.slice(cursor, index))
    parts.push(
      <mark
        key={i}
        title={`Whisper heard: "${correction.before}"`}
        className="rounded bg-emerald-100 px-0.5 text-emerald-900 dark:bg-emerald-900/50 dark:text-emerald-100"
      >
        {correction.after}
      </mark>,
    )
    cursor = index + correction.after.length
  })
  parts.push(text.slice(cursor))
  return parts
}
