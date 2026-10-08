import type { ReactNode } from 'react'

import { formatTime } from '../format'
import { initial, isSpeakerLabel, personColour } from '../people'
import type { Correction, SpeakerName, Transcript } from '../types'
import type { Player } from '../usePlayer'
import { PersonChip } from './Brand'

interface Props {
  transcript: Transcript
  corrections?: Correction[] // refined transcript only: highlight what the refiner changed
  warnings?: string[]
  speakerNames?: SpeakerName[] // refined transcript only: names identified from the recording
  player?: Player // click a line to hear it; the playing line lights up
}

interface Turn {
  speaker: string // "" when there are no speaker labels
  segments: number[]
}

export default function TranscriptView({ transcript, corrections, warnings = [], speakerNames = [], player }: Props) {
  const refined = corrections !== undefined
  const segments = transcript.segments
  const speakers = [...new Set(segments.map((s) => s.speaker).filter((s): s is string => !!s))]
  const turns = groupTurns(transcript)
  const karaoke = player && (player.playing || player.time > 0)
  const current = karaoke ? lastIndexStartedBy(transcript, player.time) : -1
  const unclear = segments.filter((s) => s.unclear).length

  return (
    <div className="flex flex-col gap-4">
      {speakers.length > 0 && (
        <ul aria-label="Speakers" className="flex flex-wrap gap-2">
          {speakers.map((speaker) => {
            const named = speakerNames.find((n) => n.name === speaker)
            return (
              <li key={speaker} title={named ? `${capitalise(named.how)}: “${named.quote}” (${formatTime(named.start)})` : undefined}>
                <PersonChip name={speaker} suffix={refined && isSpeakerLabel(speaker) ? ' · not named' : undefined} />
              </li>
            )
          })}
        </ul>
      )}

      {refined && corrections.length > 0 && (
        <p className="flex flex-wrap items-center gap-2 text-sm text-muted">
          <span className="font-semibold text-ink">Fixed:</span>
          {corrections.map((c, i) => (
            <span key={i} className="chip bg-orange-soft font-mono text-[13px] font-medium text-ink-2">
              <s className="text-faint">{c.before || '∅'}</s> → <span className="font-semibold text-orange-ink">{c.after || '∅'}</span>
            </span>
          ))}
        </p>
      )}

      <ol className="flex flex-col gap-2.5" aria-label="Transcript">
        {turns.map((turn, t) => {
          const playingHere = turn.segments.includes(current)
          const colour = turn.speaker ? personColour(turn.speaker) : null
          return (
            <li key={t} className="flex items-start gap-3">
              {colour && (
                <span className={`mt-0.5 flex size-[34px] shrink-0 items-center justify-center rounded-full text-[13px] font-bold text-white ${colour.solid}`} aria-hidden>
                  {initial(turn.speaker)}
                </span>
              )}
              <div
                className={`max-w-[680px] min-w-0 rounded-[4px_20px_20px_20px] border-2 px-4 py-3 transition-colors ${
                  playingHere ? 'glow-now border-orange bg-ground' : `border-transparent ${colour ? colour.soft : 'bg-orange-soft'} bg-opacity-60`
                }`}
              >
                <p className={`mb-1 text-[13px] font-bold ${colour ? colour.ink : 'text-muted'}`}>
                  {turn.speaker && <span>{turn.speaker} </span>}
                  <span className="font-mono font-medium text-muted">{formatTime(segments[turn.segments[0]].start)}</span>
                  {playingHere && <span className="ml-2 text-xs font-bold text-orange-ink">▶ playing</span>}
                </p>
                <p className="leading-relaxed">
                  {turn.segments.map((i) => {
                    const changes = corrections?.filter((c) => c.segment_id === i) ?? []
                    const text = changes.length ? highlight(segments[i].text, changes) : segments[i].text
                    const dim = karaoke && i > current
                    const unsure = segments[i].unclear
                    const tip = unsure ? `Speech recognition was unsure here${confidenceText(segments[i].confidence)}. Worth a listen.` : undefined
                    return (
                      <span key={i} className={unsure ? 'unclear-audio' : undefined} title={tip}>
                        {player ? (
                          <button
                            type="button"
                            onClick={() => player.seek(segments[i].start)}
                            title={tip ?? `Play from ${formatTime(segments[i].start)}`}
                            className={`cursor-pointer rounded text-left transition-opacity hover:bg-orange-track/60 ${dim ? 'opacity-55' : ''} ${i === current ? 'font-semibold' : ''}`}
                          >
                            {text}
                          </button>
                        ) : (
                          text
                        )}{' '}
                      </span>
                    )
                  })}
                </p>
              </div>
            </li>
          )
        })}
      </ol>

      <p className="text-sm text-muted">
        {refined
          ? corrections.length
            ? 'Highlighted words were fixed: hover to see what was misheard.'
            : 'No misheard technical terms needed fixing.'
          : 'Exactly as the speech recognition heard it.'}
        {player && ' Click any line to play it.'}
      </p>
      {unclear > 0 && (
        <p className="flex items-center gap-2 text-sm text-sun-ink">
          <span className="unclear-audio px-1">dotted lines</span>
          {unclear === 1 ? 'is a stretch' : 'are stretches'} where speech recognition itself was unsure: worth a listen.
        </p>
      )}
      {refined && warnings.length > 0 && (
        <div className="rounded-2xl bg-sun-soft px-4 py-3 text-sm text-sun-ink">
          <p className="font-semibold">Kept the original wording here (the suggested edit wasn't safe):</p>
          <ul className="mt-1 list-disc pl-5">
            {warnings.map((warning, i) => (
              <li key={i}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** Consecutive lines by the same speaker become one chat bubble. */
function groupTurns(transcript: Transcript): Turn[] {
  const turns: Turn[] = []
  transcript.segments.forEach((segment, i) => {
    const speaker = segment.speaker ?? ''
    const last = turns.at(-1)
    if (last && last.speaker === speaker && speaker !== '') last.segments.push(i)
    else turns.push({ speaker, segments: [i] })
  })
  return turns
}

function lastIndexStartedBy(transcript: Transcript, time: number): number {
  let index = -1
  transcript.segments.forEach((segment, i) => {
    if (segment.start <= time + 0.05) index = i
  })
  return index
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
      <mark key={i} title={`Misheard as: "${correction.before}"`} className="rounded-md bg-orange-track px-1 font-semibold text-orange-ink">
        {correction.after}
      </mark>,
    )
    cursor = index + correction.after.length
  })
  parts.push(text.slice(cursor))
  return parts
}

function confidenceText(confidence: number | null | undefined): string {
  return confidence == null ? '' : ` (${Math.round(confidence * 100)}% confident)`
}

function capitalise(text: string): string {
  return text ? text[0].toUpperCase() + text.slice(1) : text
}
