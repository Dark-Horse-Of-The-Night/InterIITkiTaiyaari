// Calls to the FastAPI backend. Vite's dev proxy forwards /api to http://localhost:8000.

import type { Job, JobError } from './types'

/** A failed API call, carrying the backend's plain-English error. */
export class ApiError extends Error {
  readonly error: JobError
  readonly status: number

  constructor(error: JobError, status: number) {
    super(error.message)
    this.error = error
    this.status = status
  }
}

export const SERVER_UNREACHABLE: JobError = {
  stage: null,
  message: "Can't reach the server.",
  fix: 'Check that the backend is running (cd backend && .venv/bin/uvicorn app.main:app --reload), then try again.',
}

/** Upload a recording. Resolves with the new job, or throws ApiError (e.g. for an unsupported file). */
export function uploadMeeting(file: File, glossary: string): Promise<Job> {
  const form = new FormData()
  form.append('file', file)
  form.append('glossary', glossary)
  return request<Job>('/api/meetings', { method: 'POST', body: form })
}

/** Get a job's progress, and its result once finished. */
export function getJob(jobId: string): Promise<Job> {
  return request<Job>(`/api/meetings/${encodeURIComponent(jobId)}`)
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch {
    throw new ApiError(SERVER_UNREACHABLE, 0) // network failure
  }

  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    // not JSON; handled below
  }

  if (!response.ok) {
    const error = (body as { error?: JobError } | null)?.error
    // Our backend always sends {"error": ...}. Without it, the reply came from the dev proxy
    // because the backend isn't running.
    throw new ApiError(error ?? SERVER_UNREACHABLE, response.status)
  }
  return body as T
}
