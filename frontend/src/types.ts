// TypeScript versions of the backend's JSON (backend/app/jobs.py and backend/app/pipeline/models.py).
// Keep these in sync when the backend models change.

export interface Segment {
  start: number // seconds
  end: number
  text: string
}

export interface Transcript {
  segments: Segment[]
}

export interface Correction {
  segment_id: number
  before: string
  after: string
}

export interface RefinedTranscript extends Transcript {
  corrections: Correction[]
  warnings: string[]
}

export interface Evidence {
  segment_ids: number[]
  quote: string
  start: number | null
}

export interface Topic {
  topic: string
  points: string[]
  segment_ids: number[]
}

export interface Decision {
  text: string
  evidence: Evidence
}

export interface ActionItem {
  task: string
  owner: string | null // null = not stated in the recording -> show "Unspecified"
  deadline: string | null
  evidence: Evidence
}

export interface OpenItem {
  text: string
  kind: 'proposal' | 'question'
  raised_by: string | null
  evidence: Evidence
}

export interface MeetingRecord {
  summary: string
  minutes: Topic[]
  decisions: Decision[]
  action_items: ActionItem[]
  open_items: OpenItem[]
  warnings: string[]
}

export interface MeetingResult {
  raw_transcript: Transcript
  refined_transcript: RefinedTranscript
  record: MeetingRecord
  markdown: string
  models: Record<string, string>
  timings_seconds: Record<string, number>
}

export type StageState = 'pending' | 'running' | 'done' | 'failed'

export interface StageProgress {
  name: string
  state: StageState
  seconds: number | null
  note: string | null // e.g. "Slow response from the service. Retrying (attempt 2 of 2)…"
  detail: string | null // e.g. "Part 2 of 6"
  seconds_since_update: number | null // while running: seconds since the stage last reported progress
}

/** An error shown to the user: which stage failed, what happened, what to do. */
export interface JobError {
  stage: string | null
  message: string
  fix: string | null
}

export interface Job {
  job_id: string
  filename: string
  status: 'queued' | 'running' | 'done' | 'failed'
  stages: StageProgress[]
  result: MeetingResult | null
  error: JobError | null
}
