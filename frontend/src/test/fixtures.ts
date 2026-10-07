// Fake backend data for tests.

import { vi } from 'vitest'

import type { Job, MeetingResult, StageState } from '../types'

const STAGE_NAMES = ['Speech-to-text', 'Refiner', 'Documenter']

export function makeJob(status: Job['status'], states: StageState[], overrides: Partial<Job> = {}): Job {
  return {
    job_id: 'job-1',
    filename: 'meeting.mp3',
    status,
    stages: STAGE_NAMES.map((name, i) => ({ name, state: states[i], seconds: states[i] === 'done' ? 2.5 : null, note: null, running_seconds: null })),
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
  return {
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
}

/** Replace fetch with a fake that returns the given replies in order (objects -> 200 JSON). */
export function fakeFetch(...replies: Array<object | Response | Error>) {
  const fetchMock = vi.fn(async () => {
    const reply = replies.length > 1 ? replies.shift()! : replies[0] // last reply repeats
    if (reply instanceof Error) throw reply
    if (reply instanceof Response) return reply.clone()
    return new Response(JSON.stringify(reply), { status: 200 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

export function errorResponse(status: number, stage: string | null, message: string, fix: string | null): Response {
  return new Response(JSON.stringify({ error: { stage, message, fix } }), { status })
}
