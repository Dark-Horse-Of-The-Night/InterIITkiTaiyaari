import { useState } from 'react'

import { downloadFile, fileStem, formatSeconds, formatTime, transcriptToText } from '../format'
import type { MeetingResult } from '../types'
import { CheckIcon, DownloadIcon } from './Icons'
import RecordView from './RecordView'
import TranscriptView from './TranscriptView'

type TabId = 'record' | 'refined' | 'raw'

interface Props {
  result: MeetingResult
  filename: string
}

export default function Results({ result, filename }: Props) {
  const [tab, setTab] = useState<TabId>('record')
  const stem = fileStem(filename)
  const totalSeconds = Object.values(result.timings_seconds).reduce((sum, s) => sum + s, 0)
  const lastSegment = result.raw_transcript.segments.at(-1)
  const corrections = result.refined_transcript.corrections.length

  const tabs: { id: TabId; label: string; badge?: number }[] = [
    { id: 'record', label: 'Meeting record' },
    { id: 'refined', label: 'Refined transcript', badge: corrections },
    { id: 'raw', label: 'Raw transcript' },
  ]

  // All four files are built from data already in the browser; the server stores nothing.
  const downloads = [
    { label: 'Markdown', name: `${stem}-record.md`, content: () => result.markdown, type: 'text/markdown', primary: true },
    { label: 'JSON', name: `${stem}-record.json`, content: () => JSON.stringify(result.record, null, 2), type: 'application/json' },
    { label: 'Refined .txt', name: `${stem}-refined-transcript.txt`, content: () => transcriptToText(result.refined_transcript), type: 'text/plain' },
    { label: 'Raw .txt', name: `${stem}-raw-transcript.txt`, content: () => transcriptToText(result.raw_transcript), type: 'text/plain' },
  ]

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-5">
        <div className="min-w-0">
          <p className="mb-2 flex flex-wrap items-center gap-2 text-[13px] text-muted">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-0.5 font-medium text-accent-ink">
              <CheckIcon size={13} strokeWidth={2.6} />
              Processed in {formatSeconds(Number(totalSeconds.toFixed(1)))}
            </span>
            <span className="truncate">
              {filename}
              {lastSegment && ` · ${formatTime(lastSegment.end)} recording`}
            </span>
          </p>
          <h1 className="text-[30px] leading-[1.15] font-semibold tracking-[-0.02em] sm:text-[32px]">{meetingTitle(stem)}</h1>
        </div>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Downloads">
          {downloads.map((d) => (
            <button
              key={d.name}
              type="button"
              onClick={() => downloadFile(d.name, d.content(), d.type)}
              className={d.primary ? 'btn-primary' : 'btn-secondary'}
            >
              {d.primary && <DownloadIcon size={16} />}
              {d.label}
            </button>
          ))}
        </div>
      </div>

      <div role="tablist" aria-label="Results" className="mt-7 flex gap-1 overflow-x-auto overflow-y-hidden border-b border-line">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            onClick={() => setTab(t.id)}
            className={`-mb-px flex min-h-11 cursor-pointer items-center gap-2 border-b-2 px-3.5 text-[14.5px] whitespace-nowrap ${
              tab === t.id ? 'border-accent font-semibold text-ink' : 'border-transparent font-medium text-muted hover:text-ink'
            }`}
          >
            {t.label}
            {t.badge ? (
              <span className="rounded-full bg-accent-soft px-[7px] text-xs font-semibold text-accent-ink" aria-label={`${t.badge} correction${t.badge === 1 ? '' : 's'}`}>
                {t.badge}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="mt-6">
        {tab === 'record' && <RecordView record={result.record} result={result} />}
        {tab === 'refined' && (
          <TranscriptView
            transcript={result.refined_transcript}
            corrections={result.refined_transcript.corrections}
            warnings={result.refined_transcript.warnings}
          />
        )}
        {tab === 'raw' && <TranscriptView transcript={result.raw_transcript} />}
      </div>
    </div>
  )
}

/** "sprint-planning_v2" -> "Sprint planning v2" (the record has no title, so the file name stands in). */
function meetingTitle(stem: string): string {
  const words = stem.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()
  return words ? words[0].toUpperCase() + words.slice(1) : 'Meeting record'
}
