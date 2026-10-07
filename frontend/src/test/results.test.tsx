import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import Results from '../components/Results'
import type { MeetingResult } from '../types'
import { makeResult } from './fixtures'

let saved: { name: string; blob: Blob }[] = []

beforeEach(() => {
  // jsdom can't really download files, so capture what would be saved.
  saved = []
  let lastBlob: Blob
  vi.stubGlobal('URL', { ...URL, createObjectURL: (blob: Blob) => ((lastBlob = blob), 'blob:fake'), revokeObjectURL: () => {} })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    saved.push({ name: this.download, blob: lastBlob })
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function renderResults(result: MeetingResult = makeResult()) {
  render(<Results result={result} filename="Sprint Sync.mp3" />)
  return result
}

describe('Meeting record tab', () => {
  it('shows "Unspecified" for a missing owner and deadline, and real values otherwise', () => {
    renderResults()
    const rows = within(screen.getByRole('table')).getAllByRole('row')

    expect(rows[1]).toHaveTextContent('Move the database')
    expect(rows[1]).toHaveTextContent('Priya')
    expect(rows[1]).toHaveTextContent('by Friday')
    expect(within(rows[2]).getAllByText('Unspecified')).toHaveLength(2) // owner and deadline
  })

  it('shows decisions with their source quote and time, and proposals labelled', () => {
    renderResults()

    expect(screen.getByText('Use OAuth for login')).toBeInTheDocument()
    expect(screen.getByText('We decided to use OAuth')).toBeInTheDocument()
    expect(screen.getByText('Proposal')).toBeInTheDocument()
    expect(screen.getByText(/raised by Arjun/)).toBeInTheDocument()
  })

  it('says "None recorded" for empty sections and shows check warnings', () => {
    const result = makeResult()
    result.record.decisions = []
    result.record.warnings = ["Removed owner 'Ravi' from action item 'Deploy'."]
    renderResults(result)

    expect(screen.getByText('None recorded.')).toBeInTheDocument()
    expect(screen.getByText('Notes on this record')).toBeInTheDocument()
    expect(screen.getByText(/Removed owner 'Ravi'/)).toBeInTheDocument()
  })
})

describe('Transcript tabs', () => {
  it('highlights corrections in the refined transcript with what Whisper heard', async () => {
    renderResults()
    await userEvent.click(screen.getByRole('tab', { name: /Refined transcript/ }))

    const mark = screen.getByText('CI/CD', { selector: 'mark' })
    expect(mark).toHaveAttribute('title', 'Whisper heard: "CICD"')
    expect(screen.getByText('1 term corrected')).toBeInTheDocument()
  })

  it('shows the raw transcript unchanged', async () => {
    renderResults()
    await userEvent.click(screen.getByRole('tab', { name: 'Raw transcript' }))

    expect(screen.getByText(/switching our CICD pipeline/)).toBeInTheDocument()
    expect(document.querySelector('mark')).toBeNull()
    expect(screen.getByText('01:08')).toBeInTheDocument() // timestamp of the 68 s segment
  })
})

describe('Downloads', () => {
  it('saves the Markdown and JSON from the same result data', async () => {
    const result = renderResults()

    await userEvent.click(screen.getByRole('button', { name: 'Markdown' }))
    await userEvent.click(screen.getByRole('button', { name: 'JSON' }))

    expect(saved.map((s) => s.name)).toEqual(['Sprint Sync-record.md', 'Sprint Sync-record.json'])
    expect(await saved[0].blob.text()).toBe(result.markdown)
    const json = JSON.parse(await saved[1].blob.text())
    expect(json).toEqual(result.record)
    expect(json.action_items[1].owner).toBeNull() // null stays null in JSON
  })

  it('saves transcripts as timestamped text', async () => {
    renderResults()

    await userEvent.click(screen.getByRole('button', { name: 'Raw .txt' }))

    expect(saved[0].name).toBe('Sprint Sync-raw-transcript.txt')
    expect(await saved[0].blob.text()).toContain('[00:04] Arjun proposed switching our CICD pipeline')
  })
})

describe('Speakers', () => {
  function withSpeakers() {
    const result = makeResult()
    const raw = ['Speaker 1', 'Speaker 2', 'Speaker 1']
    const refined = ['Speaker 1', 'Arjun', 'Speaker 1']
    result.raw_transcript.segments = result.raw_transcript.segments.map((s, i) => ({ ...s, speaker: raw[i] }))
    result.refined_transcript.segments = result.refined_transcript.segments.map((s, i) => ({ ...s, speaker: refined[i] }))
    result.refined_transcript.speaker_names = [
      { label: 'Speaker 2', name: 'Arjun', how: 'introduced themselves', quote: "I'm Arjun", start: 4 },
    ]
    return result
  }

  it('shows names where identified, with the evidence, and labels otherwise', async () => {
    renderResults(withSpeakers())
    await userEvent.click(screen.getByRole('tab', { name: /Refined transcript/ }))

    expect(screen.getByText('2 speakers')).toBeInTheDocument()
    expect(screen.getAllByText('Arjun').length).toBeGreaterThan(0)
    expect(screen.getByText("I'm Arjun")).toBeInTheDocument()
    expect(screen.getByText(/Introduced themselves/)).toBeInTheDocument()
    expect(screen.getByText('Not named in the recording')).toBeInTheDocument()
  })

  it('shows voice labels in the raw transcript and exports speakers in the text file', async () => {
    renderResults(withSpeakers())
    await userEvent.click(screen.getByRole('tab', { name: 'Raw transcript' }))

    expect(screen.getAllByText('Speaker 2').length).toBeGreaterThan(0)
    expect(screen.getByText(/Names are identified in the refined transcript/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Raw .txt' }))
    expect(await saved[0].blob.text()).toContain('[00:04] Speaker 2: Arjun proposed')
  })
})
