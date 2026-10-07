import type { ReactNode } from 'react'

import { formatTime } from '../format'
import type { Evidence, MeetingRecord, MeetingResult } from '../types'
import { PersonChip } from './Brand'

interface Props {
  record: MeetingRecord
  result?: MeetingResult // for the footer: which models made this
  onPlay?: (seconds: number) => void // jump the audio player to a moment
}

/** The structured meeting record, drawn from the same JSON that the downloads contain. */
export default function RecordView({ record, result, onPlay }: Props) {
  return (
    <div className="flex flex-col gap-[18px]">
      <section className="rounded-3xl bg-orange-soft px-6 py-[22px]">
        <h2 className="display mb-2 text-xl">In short</h2>
        <p className="text-[16.5px] leading-relaxed text-ink-2">{record.summary}</p>
      </section>

      <Card title="To-dos" empty={record.action_items.length === 0} emptyText="No tasks came out of this meeting.">
        <ul className="flex flex-col gap-2.5">
          {record.action_items.map((item, i) => (
            <li
              key={i}
              className={`rise-in flex items-start gap-3.5 rounded-[18px] border-2 px-4 py-3.5 ${item.owner ? 'border-line bg-ground' : 'border-sun bg-sun-soft/60'}`}
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <div className="min-w-0 flex-1">
                <p className="text-base font-semibold">{item.task}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {item.owner ? <PersonChip name={item.owner} /> : <span className="chip bg-sun text-sun-ink">Needs an owner</span>}
                  {item.deadline ? (
                    <span className="chip bg-sun-soft text-sun-ink">{item.deadline}</span>
                  ) : (
                    <span className="chip border-[1.5px] border-dashed border-line-strong text-muted">No deadline</span>
                  )}
                </div>
              </div>
              <TimeButton evidence={item.evidence} onPlay={onPlay} />
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Decided" empty={record.decisions.length === 0} emptyText="Nothing was decided.">
        <ul className="flex flex-col gap-3.5">
          {record.decisions.map((decision, i) => (
            <li key={i} className="flex items-start gap-3">
              <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-mint-soft text-mint-ink" aria-hidden>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 12.5 9.5 17 19 7.5" />
                </svg>
              </span>
              <div className="min-w-0">
                <p className="mt-0.5 text-base font-semibold">{decision.text}</p>
                <Quote evidence={decision.evidence} onPlay={onPlay} />
              </div>
            </li>
          ))}
        </ul>
      </Card>

      <Card
        title="Still open"
        empty={record.open_items.length === 0}
        emptyText="Nothing left hanging. Every proposal was settled."
      >
        <ul className="flex flex-col gap-3.5">
          {record.open_items.map((item, i) => (
            <li key={i} className="flex items-start gap-3">
              <span className={`chip mt-0.5 shrink-0 ${item.kind === 'proposal' ? 'bg-orange-soft text-orange-ink' : 'bg-sky-soft text-sky-ink'}`}>
                {item.kind === 'proposal' ? 'Proposal' : 'Question'}
              </span>
              <div className="min-w-0">
                <p className="text-base font-semibold">
                  {item.text}
                  {item.raised_by && <span className="font-normal text-muted"> · raised by {item.raised_by}</span>}
                </p>
                <Quote evidence={item.evidence} onPlay={onPlay} />
              </div>
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Minutes" empty={record.minutes.length === 0} emptyText="None recorded.">
        <div className="grid grid-cols-1 gap-x-8 gap-y-5 md:grid-cols-2">
          {record.minutes.map((topic, i) => (
            <div key={i}>
              <h3 className="mb-1.5 font-bold">{topic.topic}</h3>
              <ul className="flex list-disc flex-col gap-1 pl-5 text-[15px] text-ink-2 marker:text-orange">
                {topic.points.map((point, j) => (
                  <li key={j}>{point}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Card>

      {record.warnings.length > 0 && (
        <Card title="Notes on this record">
          <p className="mb-2 text-sm text-muted">Automatic checks adjusted the following:</p>
          <ul className="flex list-disc flex-col gap-1.5 pl-5 text-[14.5px] text-ink-2">
            {record.warnings.map((warning, i) => (
              <li key={i}>{warning}</li>
            ))}
          </ul>
        </Card>
      )}

      {result && (
        <p className="mt-1 text-center text-[13px] text-faint">
          {modelLine(result.models)} · every item checked against the recording
        </p>
      )}
    </div>
  )
}

function Card({ title, empty = false, emptyText, children }: { title: string; empty?: boolean; emptyText?: string; children: ReactNode }) {
  return (
    <section className="rounded-3xl border-2 border-line px-6 py-[22px]">
      <h2 className="display mb-3.5 text-xl">{title}</h2>
      {empty ? <p className="text-muted">{emptyText}</p> : children}
    </section>
  )
}

function TimeButton({ evidence, onPlay }: { evidence: Evidence; onPlay?: (seconds: number) => void }) {
  if (evidence.start === null) return null
  const label = formatTime(evidence.start).replace(/^0/, '')
  if (!onPlay) return <span className="font-mono text-[12.5px] text-muted">{label}</span>
  return (
    <button
      type="button"
      onClick={() => onPlay(evidence.start ?? 0)}
      title={`"${evidence.quote}"`}
      aria-label={`Play from ${label}`}
      className="focus-ring flex min-h-8 shrink-0 cursor-pointer items-center gap-1.5 rounded-full bg-orange-soft px-2.5 font-mono text-[12.5px] text-orange-ink transition-transform hover:scale-105"
    >
      <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
        <path d="M6 4v16l14-8z" />
      </svg>
      {label}
    </button>
  )
}

function Quote({ evidence, onPlay }: { evidence: Evidence; onPlay?: (seconds: number) => void }) {
  return (
    <p className="mt-1.5 flex flex-wrap items-center gap-2 text-sm text-muted">
      <TimeButton evidence={evidence} onPlay={onPlay} />
      <q className="italic">{evidence.quote}</q>
    </p>
  )
}

/** "Transcribed with whisper-large-v3 · refined and written with gpt-oss-20b" */
function modelLine(models: Record<string, string>): string {
  const short = (name: string | undefined) => name?.replace(/^openai\//, '') ?? '?'
  const refiner = short(models['Refiner'])
  const documenter = short(models['Documenter'])
  const writing = refiner === documenter ? `refined and written with ${refiner}` : `refined with ${refiner}, written with ${documenter}`
  return `Transcribed with ${short(models['Speech-to-text'])} · ${writing}`
}
