import { useState } from 'react'

import { downloadFile, fileStem, formatSeconds, formatTime, transcriptToText } from '../format'
import { assignPeopleColours } from '../people'
import type { MeetingResult } from '../types'
import { usePlayer } from '../usePlayer'
import AudioPlayer from './AudioPlayer'
import RecordView from './RecordView'
import TranscriptView from './TranscriptView'

type TabId = 'record' | 'refined' | 'raw'

interface Props {
  result: MeetingResult
  filename: string
  file?: File | null // the recording, for the audio player
}

export default function Results({ result, filename, file = null }: Props) {
  const [tab, setTab] = useState<TabId>('record')
  const player = usePlayer(file)
  const stem = fileStem(filename)
  const totalSeconds = Object.values(result.timings_seconds).reduce((sum, s) => sum + s, 0)
  const lastSegment = result.raw_transcript.segments.at(-1)
  const corrections = result.refined_transcript.corrections.length
  const speakerNames = [...new Set(result.refined_transcript.segments.map((s) => s.speaker).filter((s): s is string => !!s))]
  const speakers = speakerNames.length
  // Speakers first (in speaking order), then any other owners: each person gets their own colour.
  assignPeopleColours([...speakerNames, ...result.record.action_items.map((a) => a.owner ?? '').filter(Boolean)])

  const tabs: { id: TabId; label: string; badge?: number }[] = [
    { id: 'record', label: 'Meeting record' },
    { id: 'refined', label: 'Refined transcript', badge: corrections },
    { id: 'raw', label: 'Raw transcript' },
  ]
  const stats = [
    { label: count(result.record.decisions.length, 'decision'), tone: 'bg-orange-soft text-orange-ink' },
    { label: count(result.record.action_items.length, 'to-do'), tone: 'bg-sun-soft text-sun-ink' },
    { label: `${count(corrections, 'term')} fixed`, tone: 'bg-mint-soft text-mint-ink' },
    ...(speakers ? [{ label: count(speakers, 'speaker'), tone: 'bg-sky-soft text-sky-ink' }] : []),
  ]

  // All four files are built from data already in the browser; the server stores nothing.
  const downloads = [
    { label: 'Markdown', name: `${stem}-record.md`, content: () => result.markdown, type: 'text/markdown', primary: true },
    { label: 'JSON', name: `${stem}-record.json`, content: () => JSON.stringify(result.record, null, 2), type: 'application/json' },
    { label: 'Refined .txt', name: `${stem}-refined-transcript.txt`, content: () => transcriptToText(result.refined_transcript), type: 'text/plain' },
    { label: 'Raw .txt', name: `${stem}-raw-transcript.txt`, content: () => transcriptToText(result.raw_transcript), type: 'text/plain' },
  ]

  return (
    <div className="mx-auto max-w-[880px] pt-2">
      <div className="rise-in flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="display text-[40px] leading-[1.02] sm:text-[48px]">{meetingTitle(stem)}</h1>
          <p className="mt-1.5 truncate text-[15px] text-muted">
            {filename}
            {lastSegment && ` · ${formatTime(lastSegment.end).replace(/^0/, '')}`} · Processed in{' '}
            {formatSeconds(Number(totalSeconds.toFixed(1)))}
          </p>
        </div>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Downloads">
          {downloads.map((d) => (
            <button
              key={d.name}
              type="button"
              onClick={() => downloadFile(d.name, d.content(), d.type)}
              className={`focus-ring text-sm ${d.primary ? 'btn-orange' : 'btn-outline'}`}
            >
              {d.label}
            </button>
          ))}
        </div>
      </div>

      {player.available && (
        <div className="rise-in mt-6 [animation-delay:80ms]">
          <AudioPlayer player={player} file={file} fallbackDuration={lastSegment?.end ?? 0} />
        </div>
      )}

      <ul aria-label="At a glance" className="rise-in mt-4 flex flex-wrap gap-2 [animation-delay:140ms]">
        {stats.map((stat) => (
          <li key={stat.label} className={`rounded-full px-3.5 py-1.5 text-sm font-semibold ${stat.tone}`}>
            {stat.label}
          </li>
        ))}
      </ul>

      <div role="tablist" aria-label="Results" className="mt-7 flex flex-wrap gap-1.5">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            onClick={() => setTab(t.id)}
            className={`focus-ring flex min-h-11 cursor-pointer items-center gap-2 rounded-full px-[18px] text-[15px] transition-colors ${
              tab === t.id ? 'bg-ink font-bold text-white' : 'font-semibold text-muted hover:bg-orange-soft hover:text-ink'
            }`}
          >
            {t.label}
            {t.badge ? (
              <span
                className={`rounded-full px-2 text-xs font-bold ${tab === t.id ? 'bg-white text-orange-ink' : 'bg-orange-soft text-orange-ink'}`}
                aria-label={`${t.badge} correction${t.badge === 1 ? '' : 's'}`}
              >
                {t.badge}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} key={tab} className="rise-in mt-5">
        {tab === 'record' && <RecordView record={result.record} result={result} onPlay={player.available ? player.seek : undefined} />}
        {tab === 'refined' && (
          <TranscriptView
            transcript={result.refined_transcript}
            corrections={result.refined_transcript.corrections}
            warnings={result.refined_transcript.warnings}
            speakerNames={result.refined_transcript.speaker_names}
            player={player.available ? player : undefined}
          />
        )}
        {tab === 'raw' && <TranscriptView transcript={result.raw_transcript} player={player.available ? player : undefined} />}
      </div>
    </div>
  )
}

/** "sprint-planning_v2" -> "Sprint planning v2" (the record has no title, so the file name stands in). */
function meetingTitle(stem: string): string {
  const words = stem.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()
  return words ? words[0].toUpperCase() + words.slice(1) : 'Meeting record'
}

function count(n: number, noun: string): string {
  return `${n} ${noun}${n === 1 ? '' : 's'}`
}
