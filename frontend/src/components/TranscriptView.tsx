import type { ReactNode } from 'react'

import { formatTime } from '../format'
import type { Correction, SpeakerName, Transcript } from '../types'

interface Props {
  transcript: Transcript
  corrections?: Correction[] // refined transcript only: highlight what the refiner changed
  warnings?: string[]
  speakerNames?: SpeakerName[] // refined transcript only: names identified from the recording
}

// One colour per speaker, in order of first speaking (repeats after five).
const SPEAKER_DOTS = ['bg-accent', 'bg-question-ink', 'bg-proposal-ink', 'bg-danger-strong', 'bg-ink-2']

export default function TranscriptView({ transcript, corrections, warnings = [], speakerNames = [] }: Props) {
  const refined = corrections !== undefined
  const speakers = [...new Set(transcript.segments.map((s) => s.speaker).filter((s): s is string => !!s))]
  const dotFor = (speaker: string) => SPEAKER_DOTS[speakers.indexOf(speaker) % SPEAKER_DOTS.length]
  return (
    <div className="flex flex-wrap items-start gap-6">
      <section className="card min-w-0 flex-[999_1_600px] py-2" aria-label="Transcript">
        <ol>
          {transcript.segments.map((segment, i) => {
            const changes = corrections?.filter((c) => c.segment_id === i) ?? []
            const newTurn = !!segment.speaker && segment.speaker !== transcript.segments[i - 1]?.speaker
            return (
              <li key={i} className={`flex gap-[18px] px-6 py-2.5 leading-relaxed ${changes.length ? 'bg-accent-soft/40' : ''} ${newTurn && i > 0 ? 'mt-1.5' : ''}`}>
                <span className="w-11 shrink-0 pt-0.5 font-mono text-[12.5px] text-faint">{formatTime(segment.start)}</span>
                <span className="min-w-0">
                  {newTurn && segment.speaker && (
                    <span className="mb-0.5 flex items-center gap-1.5 text-[13px]">
                      <span className={`size-2 rounded-full ${dotFor(segment.speaker)}`} aria-hidden />
                      <span className={isLabel(segment.speaker) ? 'text-muted' : 'font-semibold text-ink'}>{segment.speaker}</span>
                    </span>
                  )}
                  <span className="text-ink">{changes.length ? highlight(segment.text, changes) : segment.text}</span>
                </span>
              </li>
            )
          })}
        </ol>
      </section>

      <aside className="flex min-w-0 flex-[1_1_280px] flex-col gap-4">
        {speakers.length > 0 && (
          <section className="card p-5">
            <h2 className="mb-1 text-[15px] font-semibold">
              {speakers.length} speaker{speakers.length === 1 ? '' : 's'}
            </h2>
            <p className="mb-3 text-[13.5px] text-muted">
              {refined
                ? 'Named only when the recording makes it clear. Others keep a label rather than a guess.'
                : 'Grouped by voice. Names are identified in the refined transcript.'}
            </p>
            <ul className="flex flex-col gap-2.5">
              {speakers.map((speaker) => {
                const named = speakerNames.find((n) => n.name === speaker)
                return (
                  <li key={speaker} className="flex gap-2.5">
                    <span className={`mt-[7px] size-2 shrink-0 rounded-full ${dotFor(speaker)}`} aria-hidden />
                    <div className="min-w-0 text-[13.5px]">
                      <p className={isLabel(speaker) ? 'text-muted' : 'font-semibold'}>
                        {speaker}
                        {named && <span className="font-normal text-muted"> · {named.label}</span>}
                      </p>
                      {named ? (
                        <p className="text-muted">
                          {capitalise(named.how)}: <q className="italic">{named.quote}</q>{' '}
                          <span className="font-mono text-xs">{formatTime(named.start)}</span>
                        </p>
                      ) : refined && isLabel(speaker) ? (
                        <p className="text-muted">Not named in the recording</p>
                      ) : null}
                    </div>
                  </li>
                )
              })}
            </ul>
          </section>
        )}
        {refined ? (
          <>
            <section className="card p-5">
              <h2 className="mb-1 text-[15px] font-semibold">
                {corrections.length === 0 ? 'No terms needed correcting' : `${corrections.length} term${corrections.length === 1 ? '' : 's'} corrected`}
              </h2>
              <p className="text-[13.5px] text-muted">
                {corrections.length === 0
                  ? 'The refiner found no misheard technical terms.'
                  : 'Highlighted in the transcript. Hover a highlight to see what Whisper heard.'}
              </p>
              {corrections.length > 0 && (
                <ul className="mt-3.5 flex flex-col gap-2">
                  {corrections.map((c, i) => (
                    <li key={i} className="flex items-center justify-between gap-2.5 rounded-[10px] bg-surface-2 px-3 py-2.5">
                      <span className="min-w-0 font-mono text-[13px]">
                        <s className="text-faint">{c.before || '(nothing)'}</s> <span className="text-faint">→</span>{' '}
                        <span className="font-medium text-accent-ink">{c.after || '(removed)'}</span>
                      </span>
                      {transcript.segments[c.segment_id] && (
                        <span className="font-mono text-xs text-muted">{formatTime(transcript.segments[c.segment_id].start)}</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="card p-5">
              <h2 className="mb-2.5 text-[15px] font-semibold">Protected by safety checks</h2>
              <ul className="flex list-disc flex-col gap-1 pl-[18px] text-[13.5px] text-ink-2">
                <li>Names, numbers and negations never change</li>
                <li>
                  Commitments like <em>will</em> or <em>decided</em> stay as spoken
                </li>
                <li>Edits that rewrite a sentence are rejected</li>
              </ul>
              {warnings.length === 0 ? (
                <p className="mt-3 border-t border-line-soft pt-3 text-[13px] text-muted">No edits were rejected in this meeting.</p>
              ) : (
                <div className="mt-3 border-t border-line-soft pt-3">
                  <p className="text-[13px] font-medium text-warn-ink">Edits rejected (original wording kept):</p>
                  <ul className="mt-1 flex list-disc flex-col gap-1 pl-[18px] text-[13px] text-ink-2">
                    {warnings.map((warning, i) => (
                      <li key={i}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          </>
        ) : (
          <section className="card p-5">
            <h2 className="mb-1 text-[15px] font-semibold">Exactly as heard</h2>
            <p className="text-[13.5px] text-muted">
              Whisper's original transcript, before any corrections. Compare with the refined transcript to see what changed.
            </p>
          </section>
        )}
      </aside>
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
        className="rounded bg-mark px-1 text-mark-ink underline decoration-dotted underline-offset-[3px]"
      >
        {correction.after}
      </mark>,
    )
    cursor = index + correction.after.length
  })
  parts.push(text.slice(cursor))
  return parts
}

function isLabel(speaker: string): boolean {
  return /^Speaker \d+$/.test(speaker)
}

function capitalise(text: string): string {
  return text ? text[0].toUpperCase() + text.slice(1) : text
}
