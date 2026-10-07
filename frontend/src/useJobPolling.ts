import { useEffect, useState } from 'react'

import { ApiError, getJob, SERVER_UNREACHABLE } from './api'
import type { Job, JobError } from './types'

export const POLL_INTERVAL_MS = 1000
const MAX_FAILURES_IN_A_ROW = 3 // tolerate a brief network hiccup

/**
 * Ask the backend for the job's progress every second until it is done or failed.
 * Stops automatically when the component using it goes away.
 */
export function useJobPolling(initialJob: Job): { job: Job; pollError: JobError | null } {
  const [job, setJob] = useState(initialJob)
  const [pollError, setPollError] = useState<JobError | null>(null)
  const jobId = initialJob.job_id

  useEffect(() => {
    let cancelled = false
    let failures = 0
    let timer: ReturnType<typeof setTimeout>

    async function poll() {
      try {
        const latest = await getJob(jobId)
        if (cancelled) return
        failures = 0
        setJob(latest)
        if (latest.status === 'done' || latest.status === 'failed') return // finished: stop polling
      } catch (error) {
        if (cancelled) return
        const apiError = error instanceof ApiError ? error : new ApiError(SERVER_UNREACHABLE, 0)
        failures += 1
        if (apiError.status === 404 || failures >= MAX_FAILURES_IN_A_ROW) {
          setPollError(apiError.error)
          return
        }
      }
      timer = setTimeout(poll, POLL_INTERVAL_MS)
    }

    timer = setTimeout(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [jobId])

  return { job, pollError }
}
