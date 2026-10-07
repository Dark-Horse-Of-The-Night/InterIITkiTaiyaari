import type { ReactNode } from 'react'

import { formatTime } from '../format'
import type { Evidence, MeetingRecord } from '../types'

/** The structured meeting record, drawn from the same JSON that the downloads contain. */
export default function RecordView({ record }: { record: MeetingRecord }) {
  return (
    <div className="space-y-8">
      <Section title="Summary">
        <p className="text-sm leading-relaxed text-slate-700 dark:text-slate-300">{record.summary}</p>
      </Section>

      <Section title="Minutes" empty={record.minutes.length === 0}>
        <div className="space-y-4">
          {record.minutes.map((topic, i) => (
            <div key={i}>
              <h4 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{topic.topic}</h4>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700 dark:text-slate-300">
                {topic.points.map((point, j) => (
                  <li key={j}>{point}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Key decisions" empty={record.decisions.length === 0}>
        <ol className="space-y-3">
          {record.decisions.map((decision, i) => (
            <li key={i} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
              <p className="text-sm font-medium text-slate-800 dark:text-slate-100">{decision.text}</p>
              <Source evidence={decision.evidence} />
            </li>
          ))}
        </ol>
      </Section>

      <Section title="Action items" empty={record.action_items.length === 0}>
        <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500 uppercase dark:bg-slate-800 dark:text-slate-400">
              <tr>
                <th className="px-3 py-2 font-medium">Task</th>
                <th className="px-3 py-2 font-medium">Owner</th>
                <th className="px-3 py-2 font-medium">Deadline</th>
                <th className="px-3 py-2 font-medium">Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
              {record.action_items.map((item, i) => (
                <tr key={i} className="align-top">
                  <td className="px-3 py-2 text-slate-800 dark:text-slate-100">{item.task}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{item.owner ?? <Unspecified />}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{item.deadline ?? <Unspecified />}</td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    <span className="text-xs text-slate-500 dark:text-slate-400" title={`"${item.evidence.quote}"`}>
                      {item.evidence.start !== null ? formatTime(item.evidence.start) : '—'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Open proposals and questions" empty={record.open_items.length === 0}>
        <ul className="space-y-3">
          {record.open_items.map((item, i) => (
            <li key={i} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
              <p className="text-sm text-slate-800 dark:text-slate-100">
                <span
                  className={`mr-2 rounded px-1.5 py-0.5 text-xs font-semibold ${
                    item.kind === 'proposal'
                      ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200'
                      : 'bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-200'
                  }`}
                >
                  {item.kind === 'proposal' ? 'Proposal' : 'Question'}
                </span>
                {item.text}
                {item.raised_by && <span className="text-slate-500 dark:text-slate-400"> — raised by {item.raised_by}</span>}
              </p>
              <Source evidence={item.evidence} />
            </li>
          ))}
        </ul>
      </Section>

      {record.warnings.length > 0 && (
        <Section title="Notes on this record">
          <p className="text-xs text-slate-500 dark:text-slate-400">Automatic checks adjusted the following:</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700 dark:text-slate-300">
            {record.warnings.map((warning, i) => (
              <li key={i}>{warning}</li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  )
}

function Section({ title, empty = false, children }: { title: string; empty?: boolean; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-3 text-base font-semibold text-slate-900 dark:text-white">{title}</h3>
      {empty ? <p className="text-sm text-slate-500 italic dark:text-slate-400">None recorded.</p> : children}
    </section>
  )
}

/** Shown when the recording didn't state an owner or deadline. Never filled in by guessing. */
function Unspecified() {
  return (
    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500 italic dark:bg-slate-800 dark:text-slate-400">
      Unspecified
    </span>
  )
}

function Source({ evidence }: { evidence: Evidence }) {
  return (
    <p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
      {evidence.start !== null && <span className="font-mono">{formatTime(evidence.start)}</span>}
      {evidence.start !== null && ' · '}
      <q className="italic">{evidence.quote}</q>
    </p>
  )
}
