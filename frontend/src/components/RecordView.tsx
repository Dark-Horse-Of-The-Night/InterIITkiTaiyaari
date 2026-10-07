import type { ReactNode } from 'react'

import { formatSeconds, formatTime } from '../format'
import type { Evidence, MeetingRecord, MeetingResult } from '../types'

interface Props {
  record: MeetingRecord
  result?: MeetingResult // for the sidebar: corrections, models and timings
}

/** The structured meeting record, drawn from the same JSON that the downloads contain. */
export default function RecordView({ record, result }: Props) {
  const gaps = record.action_items.filter((item) => item.owner === null || item.deadline === null)
  const unowned = record.action_items.filter((item) => item.owner === null).length

  return (
    <div className="flex flex-wrap items-start gap-6">
      <div className="flex min-w-0 flex-[999_1_600px] flex-col gap-5">
        <section className="card px-6 py-[22px]">
          <h2 className="eyebrow mb-2.5 text-muted">Summary</h2>
          <p className="text-base leading-relaxed text-ink">{record.summary}</p>
        </section>

        <Section
          title="Action items"
          aside={record.action_items.length > 0 ? `${count(record.action_items.length, 'item')}${unowned ? ` · ${unowned} without an owner` : ''}` : undefined}
          empty={record.action_items.length === 0}
        >
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] border-collapse text-[14.5px]">
              <thead>
                <tr>
                  {['Task', 'Owner', 'Deadline'].map((heading) => (
                    <th key={heading} scope="col" className="border-b border-line-soft px-3 pb-2.5 text-left text-xs font-semibold tracking-[0.04em] text-muted uppercase first:pl-0">
                      {heading}
                    </th>
                  ))}
                  <th scope="col" className="border-b border-line-soft pb-2.5 pl-3 text-right text-xs font-semibold tracking-[0.04em] text-muted uppercase">
                    Source
                  </th>
                </tr>
              </thead>
              <tbody>
                {record.action_items.map((item, i) => (
                  <tr key={i} className="align-top">
                    <td className="border-b border-line-soft py-3.5 pr-3 font-medium">{item.task}</td>
                    <td className="border-b border-line-soft px-3 py-3.5 whitespace-nowrap">
                      {item.owner ? (
                        <span className="inline-flex items-center gap-2">
                          <span className="flex size-[26px] items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent-ink" aria-hidden>
                            {item.owner.trim()[0]?.toUpperCase()}
                          </span>
                          {item.owner}
                        </span>
                      ) : (
                        <Unspecified />
                      )}
                    </td>
                    <td className="border-b border-line-soft px-3 py-3.5 whitespace-nowrap">{item.deadline ?? <Unspecified />}</td>
                    <td className="border-b border-line-soft py-3.5 pl-3 text-right">
                      <span className="time-chip" title={`"${item.evidence.quote}"`}>
                        {item.evidence.start !== null ? formatTime(item.evidence.start) : '—'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        <Section title="Key decisions" empty={record.decisions.length === 0}>
          <ol className="flex flex-col gap-4">
            {record.decisions.map((decision, i) => (
              <li key={i} className="flex items-start gap-3.5">
                <Tag tone="decision">Decided</Tag>
                <div className="min-w-0">
                  <p className="text-[15.5px] font-medium">{decision.text}</p>
                  <Source evidence={decision.evidence} />
                </div>
              </li>
            ))}
          </ol>
        </Section>

        <Section
          title="Open proposals and questions"
          subtitle="Raised in the meeting but not agreed. Not decisions, not tasks."
          empty={record.open_items.length === 0}
        >
          <ul className="flex flex-col gap-4">
            {record.open_items.map((item, i) => (
              <li key={i} className="flex items-start gap-3.5">
                <Tag tone={item.kind}>{item.kind === 'proposal' ? 'Proposal' : 'Question'}</Tag>
                <div className="min-w-0">
                  <p className="text-[15.5px] font-medium">
                    {item.text}
                    {item.raised_by && <span className="font-normal text-muted"> · raised by {item.raised_by}</span>}
                  </p>
                  <Source evidence={item.evidence} />
                </div>
              </li>
            ))}
          </ul>
        </Section>

        <Section title="Minutes" empty={record.minutes.length === 0}>
          <div className="grid grid-cols-1 gap-x-7 gap-y-5 md:grid-cols-2">
            {record.minutes.map((topic, i) => (
              <div key={i}>
                <h3 className="mb-1.5 text-[15px] font-semibold">{topic.topic}</h3>
                <ul className="flex list-disc flex-col gap-1 pl-[18px] text-[14.5px] text-ink-2">
                  {topic.points.map((point, j) => (
                    <li key={j}>{point}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Section>
      </div>

      <aside className="flex min-w-0 flex-[1_1_280px] flex-col gap-4">
        <section className="card p-5">
          <h2 className="eyebrow mb-3.5 text-muted">At a glance</h2>
          <div className="grid grid-cols-2 gap-2.5">
            <Stat value={record.decisions.length} label={record.decisions.length === 1 ? 'Decision' : 'Decisions'} />
            <Stat value={record.action_items.length} label={record.action_items.length === 1 ? 'Action item' : 'Action items'} />
            <Stat value={record.open_items.length} label={record.open_items.length === 1 ? 'Open item' : 'Open items'} />
            {result && (
              <Stat
                value={result.refined_transcript.corrections.length}
                label={result.refined_transcript.corrections.length === 1 ? 'Term corrected' : 'Terms corrected'}
              />
            )}
          </div>
        </section>

        {gaps.length > 0 && (
          <section className="rounded-2xl border border-warn-line bg-warn-soft px-5 py-[18px] text-warn-ink">
            <h2 className="mb-1.5 text-[15px] font-semibold">Gaps to follow up</h2>
            <p className="text-sm">
              {count(gaps.length, 'action item')} {gaps.length === 1 ? 'has' : 'have'} no owner or deadline in the recording:
            </p>
            <ul className="mt-1.5 flex list-disc flex-col gap-0.5 pl-[18px] text-sm italic">
              {gaps.map((item, i) => (
                <li key={i}>{item.task}</li>
              ))}
            </ul>
          </section>
        )}

        {result && (
          <section className="card p-5">
            <h2 className="eyebrow mb-3 text-muted">Processed with</h2>
            <dl className="flex flex-col gap-2.5 text-sm">
              {Object.entries(result.models).map(([stage, model]) => (
                <div key={stage}>
                  <dt className="text-[13px] text-muted">{stage}</dt>
                  <dd className="flex items-baseline justify-between gap-2">
                    <span className="truncate font-mono text-[12.5px]">{model.replace(/^openai\//, '')}</span>
                    {result.timings_seconds[stage] !== undefined && (
                      <span className="shrink-0 font-mono text-[12.5px] text-muted">{formatSeconds(result.timings_seconds[stage])}</span>
                    )}
                  </dd>
                </div>
              ))}
            </dl>
            <p className="mt-3.5 border-t border-line-soft pt-3 text-[13px] text-muted">
              Every item was checked against the transcript.{' '}
              {record.warnings.length === 0 ? 'No adjustments were needed.' : `${count(record.warnings.length, 'adjustment')} listed below.`}
            </p>
          </section>
        )}

        {record.warnings.length > 0 && (
          <section className="card p-5">
            <h2 className="mb-1 text-[15px] font-semibold">Notes on this record</h2>
            <p className="mb-2.5 text-[13px] text-muted">Automatic checks adjusted the following:</p>
            <ul className="flex list-disc flex-col gap-1.5 pl-[18px] text-[13.5px] text-ink-2">
              {record.warnings.map((warning, i) => (
                <li key={i}>{warning}</li>
              ))}
            </ul>
          </section>
        )}
      </aside>
    </div>
  )
}

function Section({ title, subtitle, aside, empty = false, children }: {
  title: string
  subtitle?: string
  aside?: string
  empty?: boolean
  children: ReactNode
}) {
  return (
    <section className="card px-6 py-[22px]">
      <div className={`flex flex-wrap items-baseline justify-between gap-3 ${subtitle ? 'mb-1' : 'mb-3.5'}`}>
        <h2 className="text-lg font-semibold tracking-[-0.01em]">{title}</h2>
        {aside && <span className="text-[13px] text-muted">{aside}</span>}
      </div>
      {subtitle && <p className="mb-3.5 text-[13.5px] text-muted">{subtitle}</p>}
      {empty ? <p className="text-sm text-muted italic">None recorded.</p> : children}
    </section>
  )
}

/** Shown when the recording didn't state an owner or deadline. Never filled in by guessing. */
function Unspecified() {
  return (
    <span className="inline-block rounded-full border border-dashed border-line-strong px-2.5 py-px text-[13px] text-muted">
      Unspecified
    </span>
  )
}

function Tag({ tone, children }: { tone: 'decision' | 'proposal' | 'question'; children: ReactNode }) {
  const colours = {
    decision: 'bg-accent-soft text-accent-ink',
    proposal: 'bg-proposal-soft text-proposal-ink',
    question: 'bg-question-soft text-question-ink',
  }[tone]
  return <span className={`mt-px shrink-0 rounded-full px-[9px] py-0.5 text-xs font-semibold ${colours}`}>{children}</span>
}

function Source({ evidence }: { evidence: Evidence }) {
  return (
    <p className="mt-2 flex flex-wrap items-baseline gap-2.5 text-sm text-ink-2">
      {evidence.start !== null && <span className="time-chip">{formatTime(evidence.start)}</span>}
      <q className="italic">{evidence.quote}</q>
    </p>
  )
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div className="rounded-xl bg-surface-2 px-3.5 py-3">
      <p className="text-[26px] leading-tight font-semibold tracking-[-0.02em]">{value}</p>
      <p className="text-[13px] text-muted">{label}</p>
    </div>
  )
}

function count(n: number, noun: string): string {
  return `${n} ${noun}${n === 1 ? '' : 's'}`
}
