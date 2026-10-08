import { formatTime } from '../format'
import { initial, personColour } from '../people'
import type { SpeakingStats } from '../types'

/** Talk time, share and questions per person, worked out by code from the speaker labels. */
export function WhoSpoke({ speaking }: { speaking: SpeakingStats }) {
  return (
    <section aria-labelledby="who-spoke-title" className="rounded-3xl border-2 border-line px-6 py-[22px]">
      <h2 id="who-spoke-title" className="display mb-3.5 text-xl">
        Who spoke
      </h2>
      <ul className="flex flex-col gap-3">
        {speaking.speakers.map((s, i) => {
          const colour = personColour(s.speaker)
          const percent = Math.round(s.share * 100)
          return (
            <li key={s.speaker} className="flex items-center gap-3">
              <span className={`flex size-[34px] shrink-0 items-center justify-center rounded-full text-[13px] font-bold text-white ${colour.solid}`} aria-hidden>
                {initial(s.speaker)}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <p className="font-semibold">{s.speaker}</p>
                  <p className="text-[13.5px] text-muted">
                    {formatTime(s.seconds).replace(/^0/, '')} · {plural(s.turns, 'turn')}
                    {s.questions > 0 && ` · ${plural(s.questions, 'question')}`}
                  </p>
                </div>
                <div className="mt-1 flex items-center gap-2.5">
                  <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-stone-soft">
                    <div
                      className={`bar-grow h-full rounded-full ${colour.solid}`}
                      style={{ width: `${Math.max(2, percent)}%`, animationDelay: `${i * 80}ms` }}
                    />
                  </div>
                  <span className="w-10 text-right font-mono text-[13px] font-semibold">{percent}%</span>
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

/** A strip showing who held the floor when. Click a block to play from there. */
export function SpeakingTimeline({ speaking, duration, onPlay }: { speaking: SpeakingStats; duration: number; onPlay?: (seconds: number) => void }) {
  const end = Math.max(duration, ...speaking.timeline.map((turn) => turn.end)) || 1
  return (
    <div className="mt-3">
      <p className="mb-1.5 text-[13px] font-semibold text-muted">Who spoke when</p>
      <div role="list" aria-label="Who spoke when" className="relative h-5 overflow-hidden rounded-full bg-stone-soft">
        {speaking.timeline.map((turn, i) => {
          const colour = personColour(turn.speaker)
          const label = `${turn.speaker}, ${formatTime(turn.start)}–${formatTime(turn.end)}`
          const style = { left: `${(turn.start / end) * 100}%`, width: `max(3px, ${((turn.end - turn.start) / end) * 100}%)` }
          return onPlay ? (
            <button
              key={i}
              type="button"
              role="listitem"
              title={label}
              aria-label={`Play ${label}`}
              onClick={() => onPlay(turn.start)}
              className={`focus-ring absolute top-0 h-full cursor-pointer border-r-2 border-white transition-opacity hover:opacity-75 ${colour.solid}`}
              style={style}
            />
          ) : (
            <span key={i} role="listitem" title={label} aria-label={label} className={`absolute top-0 h-full border-r-2 border-white ${colour.solid}`} style={style} />
          )
        })}
      </div>
    </div>
  )
}

function plural(n: number, noun: string): string {
  return `${n} ${noun}${n === 1 ? '' : 's'}`
}
