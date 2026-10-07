import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import JobView from '../components/JobView'
import { POLL_INTERVAL_MS } from '../useJobPolling'
import { errorResponse, fakeFetch, makeJob, makeResult } from './fixtures'

const queued = makeJob('queued', ['pending', 'pending', 'pending'])

async function nextPoll() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
  })
}

function stageState(label: string): string | null {
  return screen.getByText(label).closest('li')!.getAttribute('data-state')
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('JobView progress', () => {
  it('shows each stage moving forward and stops polling when done', async () => {
    const fetchMock = fakeFetch(
      makeJob('running', ['running', 'pending', 'pending']),
      makeJob('running', ['done', 'running', 'pending']),
      makeJob('done', ['done', 'done', 'done'], { result: makeResult() }),
    )
    render(<JobView initialJob={queued} onReset={() => {}} />)
    expect(stageState('Transcribing the audio')).toBe('pending')

    await nextPoll()
    expect(stageState('Transcribing the audio')).toBe('running')

    await nextPoll()
    expect(stageState('Transcribing the audio')).toBe('done')
    expect(screen.getAllByText('Done in 2.5s')).toHaveLength(1)
    expect(stageState('Refining technical terms')).toBe('running')

    await nextPoll() // done: progress folds into a one-line summary above the results
    expect(screen.getByText(/Processed/)).toHaveTextContent('Processed meeting.mp3 in 2.5s')

    const callsWhenDone = fetchMock.mock.calls.length
    await nextPoll()
    await nextPoll()
    expect(fetchMock.mock.calls.length).toBe(callsWhenDone) // no more polling
  })

  it('shows the failed stage with its message and fix', async () => {
    const error = { stage: 'Refiner', message: 'Refiner failed: the API key was rejected.', fix: 'Check REFINER_API_KEY in backend/.env.' }
    const fetchMock = fakeFetch(makeJob('failed', ['done', 'failed', 'pending'], { error }))
    render(<JobView initialJob={queued} onReset={() => {}} />)

    await nextPoll()

    expect(stageState('Refining technical terms')).toBe('failed')
    expect(screen.getByRole('alert')).toHaveTextContent('Stage: Refiner')
    expect(screen.getByRole('alert')).toHaveTextContent('Check REFINER_API_KEY')
    await nextPoll()
    expect(fetchMock).toHaveBeenCalledTimes(1) // stopped after failure
  })

  it('stops with a clear message when the job is not found', async () => {
    fakeFetch(errorResponse(404, null, 'This processing job was not found.', 'Upload the recording again.'))
    render(<JobView initialJob={queued} onReset={() => {}} />)

    await nextPoll()

    expect(screen.getByRole('alert')).toHaveTextContent('This processing job was not found.')
  })

  it('tolerates a brief network hiccup', async () => {
    fakeFetch(new TypeError('Failed to fetch'), makeJob('running', ['running', 'pending', 'pending']))
    render(<JobView initialJob={queued} onReset={() => {}} />)

    await nextPoll() // fails once
    await nextPoll() // recovers

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(stageState('Transcribing the audio')).toBe('running')
  })

  it('gives up after repeated network failures', async () => {
    fakeFetch(new TypeError('Failed to fetch'))
    render(<JobView initialJob={queued} onReset={() => {}} />)

    await nextPoll()
    await nextPoll()
    await nextPoll()

    expect(screen.getByRole('alert')).toHaveTextContent("Can't reach the server.")
  })
})
