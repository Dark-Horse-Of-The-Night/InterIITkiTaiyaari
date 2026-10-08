import { useState } from 'react'

import type { TrustReport as Trust } from '../types'

/** What the automatic checks verified, removed or blocked. Every number comes from code, not a model. */
export default function TrustReport({ trust }: { trust: Trust }) {
  const [open, setOpen] = useState(false)
  const blocked = Object.values(trust.edits_blocked).reduce((sum, n) => sum + n, 0)
  const guesses = trust.items_removed + trust.details_removed
  const speakers = trust.speakers_named + trust.speakers_unnamed

  const tiles = [
    { value: trust.items_verified, label: 'items backed by a quote', hint: 'Every decision, task and open item quotes the transcript', tone: 'bg-mint-soft text-mint-ink' },
    { value: guesses, label: guesses === 1 ? 'guess removed' : 'guesses removed', hint: 'Invented items, owners or deadlines the checks threw out', tone: 'bg-orange-soft text-orange-ink' },
    { value: blocked, label: blocked === 1 ? 'risky edit blocked' : 'risky edits blocked', hint: blockedHint(trust.edits_blocked), tone: 'bg-sky-soft text-sky-ink' },
    { value: trust.unclear_segments, label: trust.unclear_segments === 1 ? 'unclear audio spot' : 'unclear audio spots', hint: 'Lines where speech recognition itself was unsure', tone: 'bg-sun-soft text-sun-ink' },
  ]

  const facts = [
    `${plural(trust.owners_unspecified, 'owner')} and ${plural(trust.deadlines_unspecified, 'deadline')} left Unspecified because nobody said them`,
    ...(speakers ? [`${trust.speakers_named} of ${plural(speakers, 'speaker')} named from evidence in the recording`] : []),
    ...(trust.unclear_items ? [`${plural(trust.unclear_items, 'item')} in this record quote unclear audio: marked “check audio”`] : []),
    ...(trust.items_superseded ? [`${plural(trust.items_superseded, 'item')} replaced by a later outcome in the meeting`] : []),
  ]

  return (
    <section aria-labelledby="trust-title" className="rounded-3xl border-2 border-line px-6 py-[22px]">
      <div className="mb-3.5 flex items-center gap-2.5">
        <span className="flex size-8 items-center justify-center rounded-full bg-mint-soft text-mint-ink" aria-hidden>
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.4 7.5 9.5 4.3-1.1 7.5-4.9 7.5-9.5V6z" />
            <path d="m8.8 12.2 2.3 2.3 4.3-4.6" />
          </svg>
        </span>
        <h2 id="trust-title" className="display text-xl">
          Trust report
        </h2>
        <span className="text-sm text-muted">· checked by code against the recording</span>
      </div>

      <ul className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
        {tiles.map((tile, i) => (
          <li key={tile.label} title={tile.hint} className={`pop-in rounded-[18px] px-4 py-3 ${tile.tone}`} style={{ animationDelay: `${i * 70}ms` }}>
            <p className="display text-[30px] leading-none">{tile.value}</p>
            <p className="mt-1 text-[13.5px] font-semibold leading-snug">{tile.label}</p>
          </li>
        ))}
      </ul>

      <ul className="mt-3.5 flex flex-col gap-1 text-[14.5px] text-ink-2">
        {facts.map((fact) => (
          <li key={fact} className="flex gap-2">
            <span className="text-mint-ink" aria-hidden>
              ✓
            </span>
            {fact}
          </li>
        ))}
      </ul>

      {trust.notes.length > 0 && (
        <div className="mt-3">
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen(!open)}
            className="focus-ring cursor-pointer rounded-full text-sm font-bold text-orange-ink hover:underline"
          >
            {open ? 'Hide' : 'See'} what the checks changed ({trust.notes.length})
          </button>
          {open && (
            <ul className="rise-in mt-2 flex list-disc flex-col gap-1.5 pl-5 text-[14px] text-ink-2">
              {trust.notes.map((note, i) => (
                <li key={i}>{note}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}

function blockedHint(reasons: Record<string, number>): string {
  const entries = Object.entries(reasons)
  if (!entries.length) return 'Corrections that would change a number, negation or commitment are refused'
  return 'Refused because the edit ' + entries.map(([reason, n]) => `${reason} (${n})`).join(', ')
}

function plural(n: number, noun: string): string {
  return `${n} ${noun}${n === 1 ? '' : 's'}`
}
