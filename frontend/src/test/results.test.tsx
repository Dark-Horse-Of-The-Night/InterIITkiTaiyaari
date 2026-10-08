import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import Results from '../components/Results'
import type { MeetingResult } from '../types'
import { makeResult } from './fixtures'

let saved: { name: string; blob: Blob }[] = []
let played: number[] = []

beforeEach(() => {
  // jsdom can't really download files or play audio, so capture what would happen.
  saved = []
  played = []
  let lastBlob: Blob
  vi.stubGlobal('URL', { ...URL, createObjectURL: (blob: Blob) => ((lastBlob = blob), 'blob:fake'), revokeObjectURL: () => {} })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    saved.push({ name: this.download, blob: lastBlob })
  })
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(function (this: HTMLMediaElement) {
    played.push(this.currentTime)
    return Promise.resolve()
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function renderResults(result: MeetingResult = makeResult(), file: File | null = null) {
  render(<Results result={result} filename="Sprint Sync.mp3" file={file} />)
  return result
}

const recording = () => new File([new Uint8Array(1000)], 'Sprint Sync.mp3', { type: 'audio/mpeg' })

describe('Meeting record tab', () => {
  it('shows to-dos with owners and deadlines, and flags missing ones instead of guessing', () => {
    renderResults()
    const todos = within(screen.getByRole('heading', { name: 'To-dos' }).parentElement!).getAllByRole('listitem')

    expect(todos[0]).toHaveTextContent('Move the database')
    expect(todos[0]).toHaveTextContent('Priya')
    expect(todos[0]).toHaveTextContent('by Friday')
    expect(todos[1]).toHaveTextContent('Update the Swagger docs')
    expect(within(todos[1]).getByText('Needs an owner')).toBeInTheDocument()
    expect(within(todos[1]).getByText('No deadline')).toBeInTheDocument()
  })

  it('shows decisions and open proposals with their quotes', () => {
    renderResults()

    expect(screen.getByText('Use OAuth for login')).toBeInTheDocument()
    expect(screen.getByText('We decided to use OAuth')).toBeInTheDocument()
    expect(screen.getByText('Proposal')).toBeInTheDocument()
    expect(screen.getByText(/raised by Arjun/)).toBeInTheDocument()
  })

  it('shows friendly empty states and check warnings', () => {
    const result = makeResult()
    result.record.decisions = []
    result.record.warnings = ["Removed owner 'Ravi' from action item 'Deploy'."]
    renderResults(result)

    expect(screen.getByText('Nothing was decided.')).toBeInTheDocument()
    expect(screen.getByText('Notes on this record')).toBeInTheDocument()
    expect(screen.getByText(/Removed owner 'Ravi'/)).toBeInTheDocument()
  })

  it('shows quick stats at the top', () => {
    renderResults()
    const stats = screen.getByRole('list', { name: 'At a glance' })

    expect(stats).toHaveTextContent('1 decision')
    expect(stats).toHaveTextContent('2 to-dos')
    expect(stats).toHaveTextContent('1 term fixed')
  })
})

describe('Audio player', () => {
  it('is hidden without a recording', () => {
    renderResults()
    expect(screen.queryByRole('region', { name: 'Audio player' })).not.toBeInTheDocument()
  })

  it('plays from a to-do or quote when its time is clicked', async () => {
    renderResults(makeResult(), recording())

    expect(screen.getByRole('region', { name: 'Audio player' })).toBeInTheDocument()
    await userEvent.click(screen.getAllByRole('button', { name: 'Play from 1:08' })[0])

    expect(played).toEqual([68])
  })

  it('plays from a transcript line when it is clicked', async () => {
    renderResults(makeResult(), recording())
    await userEvent.click(screen.getByRole('tab', { name: /Refined transcript/ }))

    await userEvent.click(screen.getByRole('button', { name: /Someone needs to update the Swagger docs/ }))

    expect(played).toEqual([68])
  })
})

describe('Transcript tabs', () => {
  it('highlights corrections in the refined transcript with what was misheard', async () => {
    renderResults()
    await userEvent.click(screen.getByRole('tab', { name: /Refined transcript/ }))

    const mark = screen.getByText('CI/CD', { selector: 'mark' })
    expect(mark).toHaveAttribute('title', 'Misheard as: "CICD"')
    expect(screen.getByText('Fixed:')).toBeInTheDocument()
  })

  it('shows the raw transcript unchanged', async () => {
    renderResults()
    await userEvent.click(screen.getByRole('tab', { name: 'Raw transcript' }))

    expect(screen.getByText(/switching our CICD pipeline/)).toBeInTheDocument()
    expect(document.querySelector('mark')).toBeNull()
    expect(screen.getByText('01:08')).toBeInTheDocument() // timestamp of the 68 s segment
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

  it('shows names where identified (with the evidence on hover) and labels otherwise', async () => {
    renderResults(withSpeakers())
    await userEvent.click(screen.getByRole('tab', { name: /Refined transcript/ }))
    const speakers = screen.getByRole('list', { name: 'Speakers' })

    expect(speakers).toHaveTextContent('Arjun')
    expect(speakers).toHaveTextContent('Speaker 1 · not named')
    expect(within(speakers).getAllByRole('listitem')[1]).toHaveAttribute('title', expect.stringContaining('Introduced themselves'))
    expect(screen.getByRole('list', { name: 'At a glance' })).toHaveTextContent('2 speakers')
  })

  it('shows voice labels in the raw transcript and exports speakers in the text file', async () => {
    renderResults(withSpeakers())
    await userEvent.click(screen.getByRole('tab', { name: 'Raw transcript' }))

    expect(screen.getByRole('list', { name: 'Speakers' })).toHaveTextContent('Speaker 2')

    await userEvent.click(screen.getByRole('button', { name: 'Raw .txt' }))
    expect(await saved[0].blob.text()).toContain('[00:04] Speaker 2: Arjun proposed')
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
    expect(json).toMatchObject(result.record) // the record, plus the trust report
    expect(json.action_items[1].owner).toBeNull() // null stays null in JSON
  })

  it('saves transcripts as timestamped text', async () => {
    renderResults()

    await userEvent.click(screen.getByRole('button', { name: 'Raw .txt' }))

    expect(saved[0].name).toBe('Sprint Sync-raw-transcript.txt')
    expect(await saved[0].blob.text()).toContain('[00:04] Arjun proposed switching our CICD pipeline')
  })
})

function withExtras(): MeetingResult {
  const result = makeResult()
  result.refined_transcript.segments = result.refined_transcript.segments.map((s, i) => ({
    ...s,
    speaker: i === 1 ? 'Arjun' : 'Speaker 1',
    unclear: i === 2,
    confidence: i === 2 ? 0.55 : 0.88,
  }))
  result.record.action_items[1].evidence.unclear = true
  result.trust = {
    items_verified: 4,
    items_removed: 1,
    details_removed: 1,
    items_superseded: 0,
    owners_unspecified: 1,
    deadlines_unspecified: 1,
    corrections: 1,
    edits_blocked: { 'changed a number': 1 },
    speakers_named: 1,
    speakers_unnamed: 1,
    unclear_segments: 1,
    unclear_items: 1,
    notes: ["Removed owner 'Ravi' from action item 'Update the Swagger docs': not stated in the recording near that point."],
  }
  result.speaking = {
    speakers: [
      { speaker: 'Speaker 1', seconds: 8, share: 0.67, turns: 2, longest_turn_seconds: 4, questions: 1 },
      { speaker: 'Arjun', seconds: 4, share: 0.33, turns: 1, longest_turn_seconds: 4, questions: 0 },
    ],
    timeline: [
      { speaker: 'Speaker 1', start: 0, end: 4 },
      { speaker: 'Arjun', start: 4, end: 8 },
      { speaker: 'Speaker 1', start: 68, end: 72 },
    ],
  }
  return result
}

describe('Trust report, speaking stats and unclear audio', () => {
  it('shows the trust report counts and what the checks changed', async () => {
    renderResults(withExtras())
    const card = screen.getByRole('region', { name: 'Trust report' })

    expect(within(card).getByText('items backed by a quote').previousSibling).toHaveTextContent('4')
    expect(within(card).getByText('guesses removed').previousSibling).toHaveTextContent('2')
    expect(within(card).getByText('risky edit blocked')).toBeInTheDocument()
    expect(within(card).getByText(/1 owner and 1 deadline left Unspecified/)).toBeInTheDocument()

    await userEvent.click(within(card).getByRole('button', { name: /See what the checks changed/ }))
    expect(within(card).getByText(/Removed owner 'Ravi'/)).toBeInTheDocument()
  })

  it('marks record items that quote unclear audio', () => {
    renderResults(withExtras())
    const todos = within(screen.getByRole('heading', { name: 'To-dos' }).parentElement!).getAllByRole('listitem')

    expect(within(todos[1]).getByText('⚠ check audio')).toBeInTheDocument()
    expect(within(todos[0]).queryByText('⚠ check audio')).not.toBeInTheDocument()
  })

  it('shows who spoke how much', () => {
    renderResults(withExtras())
    const card = screen.getByRole('region', { name: 'Who spoke' })

    expect(within(card).getByText('67%')).toBeInTheDocument()
    expect(within(card).getByText(/2 turns · 1 question/)).toBeInTheDocument()
  })

  it('plays from a block on the speaking timeline', async () => {
    renderResults(withExtras(), recording())

    await userEvent.click(screen.getByRole('listitem', { name: /Play Arjun, 00:04/ }))
    expect(played).toContain(4)
  })

  it('highlights unclear lines in the transcript', async () => {
    renderResults(withExtras())
    await userEvent.click(screen.getByRole('tab', { name: /Refined transcript/ }))

    expect(screen.getByTitle(/Speech recognition was unsure here \(55% confident\)/)).toHaveTextContent('Swagger docs')
    expect(screen.getByText(/where speech recognition itself was unsure/)).toBeInTheDocument()
  })

  it('downloads the server-built JSON, which includes the trust report', async () => {
    renderResults()
    await userEvent.click(screen.getByRole('button', { name: 'JSON' }))

    expect(await saved[0].blob.text()).toContain('"trust_report"')
  })

  it('works for older results without the extras', () => {
    renderResults()

    expect(screen.queryByRole('region', { name: 'Trust report' })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Who spoke' })).not.toBeInTheDocument()
  })
})
