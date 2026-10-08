// Fake backend data for tests.

import { vi } from 'vitest'

import type { Job, MeetingResult, StageState } from '../types'

const STAGE_NAMES = ['Speech-to-text', 'Refiner', 'Documenter']

export function makeJob(status: Job['status'], states: StageState[], overrides: Partial<Job> = {}): Job {
  return {
    job_id: 'job-1',
    filename: 'meeting.mp3',
    status,
    stages: STAGE_NAMES.map((name, i) => ({ name, state: states[i], seconds: states[i] === 'done' ? 2.5 : null, note: null, detail: null, seconds_since_update: null })),
    result: null,
    error: null,
    ...overrides,
  }
}

export function makeResult(): MeetingResult {
  const segments = [
    { start: 0, end: 4, text: 'Priya will move the PostgreSQL database by Friday.' },
    { start: 4, end: 8, text: 'Arjun proposed switching our CI/CD pipeline to GitHub Actions.' },
    { start: 68, end: 72, text: 'Someone needs to update the Swagger docs.' },
  ]
  const result: MeetingResult = {
    raw_transcript: {
      segments: [segments[0], { ...segments[1], text: 'Arjun proposed switching our CICD pipeline to GitHub Actions.' }, segments[2]],
    },
    refined_transcript: {
      segments,
      corrections: [{ segment_id: 1, before: 'CICD', after: 'CI/CD' }],
      warnings: [],
    },
    record: {
      summary: 'Sprint planning covering the database and CI/CD.',
      minutes: [{ topic: 'Database', points: ['Move to a managed instance'], segment_ids: [0] }],
      decisions: [{ text: 'Use OAuth for login', evidence: { segment_ids: [0], quote: 'We decided to use OAuth', start: 0 } }],
      action_items: [
        { task: 'Move the database', owner: 'Priya', deadline: 'by Friday', evidence: { segment_ids: [0], quote: 'Priya will move', start: 0 } },
        { task: 'Update the Swagger docs', owner: null, deadline: null, evidence: { segment_ids: [2], quote: 'update the Swagger docs', start: 68 } },
      ],
      open_items: [
        { text: 'Switch to GitHub Actions', kind: 'proposal', raised_by: 'Arjun', evidence: { segment_ids: [1], quote: 'Arjun proposed', start: 4 } },
      ],
      warnings: [],
    },
    markdown: '# Meeting record\n\n| 1 | Move the database | Priya | by Friday | 00:00 |\n',
    models: { 'Speech-to-text': 'whisper-large-v3' },
    timings_seconds: { 'Speech-to-text': 2.5 },
  }
  // The server builds the JSON download from the record plus the code-made reports.
  result.record_json = JSON.stringify({ ...result.record, trust_report: { items_verified: 4 } }, null, 2)
  return result
}

/** Replace fetch with a fake that returns the given replies in order (objects -> 200 JSON).
 *  Requests for the sample list get `samples` (empty by default) and don't use up a reply. */
export function fakeFetch(...replies: Array<object | Response | Error>) {
  return fakeFetchWithSamples([], ...replies)
}

export function fakeFetchWithSamples(samples: object[], ...replies: Array<object | Response | Error>) {
  const fetchMock = vi.fn(async (url: string) => {
    if (String(url) === '/api/samples') return new Response(JSON.stringify(samples), { status: 200 })
    if (String(url).startsWith('/api/samples/')) return new Response(new Uint8Array(2000), { status: 200, headers: { 'content-type': 'audio/mp4' } })
    const reply = replies.length > 1 ? replies.shift()! : replies[0] // last reply repeats
    if (reply instanceof Error) throw reply
    if (reply instanceof Response) return reply.clone()
    return new Response(JSON.stringify(reply), { status: 200 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** The fetch calls that weren't for the sample list. */
export function apiCalls(fetchMock: ReturnType<typeof fakeFetch>) {
  return fetchMock.mock.calls.filter(([url]) => !String(url).startsWith('/api/samples'))
}

export function errorResponse(status: number, stage: string | null, message: string, fix: string | null): Response {
  return new Response(JSON.stringify({ error: { stage, message, fix } }), { status })
}
