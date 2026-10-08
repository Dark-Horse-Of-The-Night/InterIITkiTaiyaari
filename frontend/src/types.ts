// TypeScript versions of the backend's JSON (backend/app/jobs.py and backend/app/pipeline/models.py).
// Keep these in sync when the backend models change.

export interface Segment {
  start: number // seconds
  end: number
  text: string
  speaker?: string | null // a name if identified from the recording, else "Speaker 2"; absent if labels are off
  confidence?: number | null // how sure Whisper was about this stretch (0-1)
  unclear?: boolean // Whisper was unsure here: worth a listen
}

export interface Transcript {
  segments: Segment[]
}

export interface Correction {
  segment_id: number
  before: string
  after: string
}

export interface SpeakerName {
  label: string // "Speaker 2"
  name: string // "Neha"
  how: string // "introduced themselves" | "was addressed by name and answered"
  quote: string
  start: number
}

export interface RefinedTranscript extends Transcript {
  corrections: Correction[]
  warnings: string[]
  speaker_names?: SpeakerName[]
  blocked_edits?: Record<string, number> // refiner edits rejected by the code checks, by reason
}

export interface Evidence {
  segment_ids: number[]
  quote: string
  start: number | null
  unclear?: boolean // the quote comes from audio Whisper was unsure about
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

/** What the automatic checks verified, removed or blocked (computed by code, no model). */
export interface TrustReport {
  items_verified: number
  items_removed: number
  details_removed: number
  items_superseded: number
  owners_unspecified: number
  deadlines_unspecified: number
  corrections: number
  edits_blocked: Record<string, number>
  speakers_named: number
  speakers_unnamed: number
  unclear_segments: number
  unclear_items: number
  notes: string[]
}

export interface SpeakerStats {
  speaker: string
  seconds: number
  share: number // 0-1
  turns: number
  longest_turn_seconds: number
  questions: number
}

export interface SpeakingTurn {
  speaker: string
  start: number
  end: number
}

export interface SpeakingStats {
  speakers: SpeakerStats[] // most talk time first
  timeline: SpeakingTurn[]
}

export interface MeetingResult {
  raw_transcript: Transcript
  refined_transcript: RefinedTranscript
  record: MeetingRecord
  trust?: TrustReport
  speaking?: SpeakingStats | null // null when there are no speaker labels
  markdown: string
  record_json?: string // the JSON download, built by the server from the same data as `markdown`
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

/** A correction shared as soon as the refiner finishes (for the live fix-it view). */
export interface PreviewCorrection {
  before: string
  after: string
  sentence: string
}

export interface Job {
  job_id: string
  filename: string
  status: 'queued' | 'running' | 'done' | 'failed'
  stages: StageProgress[]
  preview?: PreviewCorrection[] | null
  result: MeetingResult | null
  error: JobError | null
}

/** A sample recording the app can try ("Try one of ours"). */
export interface Sample {
  id: string
  title: string
  filename: string
  seconds: number
}
