import { useState } from 'react'

import { downloadFile, fileStem, transcriptToText } from '../format'
import type { MeetingResult } from '../types'
import RecordView from './RecordView'
import TranscriptView from './TranscriptView'

const TABS = [
  { id: 'record', label: 'Meeting record' },
  { id: 'refined', label: 'Refined transcript' },
  { id: 'raw', label: 'Raw transcript' },
] as const

type TabId = (typeof TABS)[number]['id']

interface Props {
  result: MeetingResult
  filename: string
}

export default function Results({ result, filename }: Props) {
  const [tab, setTab] = useState<TabId>('record')
  const stem = fileStem(filename)

  // All four files are built from data already in the browser; the server stores nothing.
  const downloads = [
    { label: 'Record (.md)', name: `${stem}-record.md`, content: () => result.markdown, type: 'text/markdown' },
    { label: 'Record (.json)', name: `${stem}-record.json`, content: () => JSON.stringify(result.record, null, 2), type: 'application/json' },
    { label: 'Refined transcript', name: `${stem}-refined-transcript.txt`, content: () => transcriptToText(result.refined_transcript), type: 'text/plain' },
    { label: 'Raw transcript', name: `${stem}-raw-transcript.txt`, content: () => transcriptToText(result.raw_transcript), type: 'text/plain' },
  ]

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2">
        {downloads.map((d) => (
          <button
            key={d.name}
            type="button"
            onClick={() => downloadFile(d.name, d.content(), d.type)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            ↓ {d.label}
          </button>
        ))}
      </div>

      <div role="tablist" aria-label="Results" className="flex gap-1 border-b border-slate-200 dark:border-slate-700">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            onClick={() => setTab(t.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              tab === t.id
                ? 'border-indigo-600 text-indigo-700 dark:border-indigo-400 dark:text-indigo-300'
                : 'border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === 'record' && <RecordView record={result.record} />}
        {tab === 'refined' && (
          <TranscriptView
            transcript={result.refined_transcript}
            corrections={result.refined_transcript.corrections}
            warnings={result.refined_transcript.warnings}
          />
        )}
        {tab === 'raw' && <TranscriptView transcript={result.raw_transcript} />}
      </div>

      <p className="text-xs text-slate-400 dark:text-slate-500">
        Models: {Object.entries(result.models).map(([stage, model]) => `${stage}: ${model}`).join(' · ')}
      </p>
    </div>
  )
}
