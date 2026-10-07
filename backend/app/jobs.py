"""In-memory store of processing jobs, so the frontend can poll for progress.

Jobs live only while the server runs (a restart forgets them) and are removed
an hour after they finish. That's enough for a single-user demo app.
"""

import threading
import time
import uuid
from typing import Literal

from pydantic import BaseModel

from app.pipeline.run import STAGES, MeetingResult

JOB_TTL_SECONDS = 60 * 60


class StageProgress(BaseModel):
    name: str
    state: Literal["pending", "running", "done", "failed"] = "pending"
    seconds: float | None = None


class JobError(BaseModel):
    """A failure shown to the user: which stage, what happened, what to do."""

    stage: str | None
    message: str
    fix: str | None


class Job(BaseModel):
    job_id: str
    filename: str
    status: Literal["queued", "running", "done", "failed"] = "queued"
    stages: list[StageProgress]
    result: MeetingResult | None = None
    error: JobError | None = None
    finished_at: float | None = None


class JobStore:
    """Thread-safe: jobs are updated from background threads while the API reads them."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, filename: str) -> Job:
        with self._lock:
            self._remove_expired()
            job = Job(job_id=uuid.uuid4().hex, filename=filename, stages=[StageProgress(name=s) for s in STAGES])
            self._jobs[job.job_id] = job
            return job.model_copy(deep=True)

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy(deep=True) if job else None

    def update_stage(self, job_id: str, stage: str, state: Literal["running", "done"], seconds: float | None) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            for progress in job.stages:
                if progress.name == stage:
                    progress.state = state
                    progress.seconds = seconds

    def finish(self, job_id: str, result: MeetingResult) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "done"
            job.result = result
            job.finished_at = time.time()

    def fail(self, job_id: str, error: JobError) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "failed"
            job.error = error
            job.finished_at = time.time()
            for progress in job.stages:
                if progress.state == "running":
                    progress.state = "failed"

    def _remove_expired(self) -> None:
        cutoff = time.time() - JOB_TTL_SECONDS
        for job_id in [j.job_id for j in self._jobs.values() if j.finished_at and j.finished_at < cutoff]:
            del self._jobs[job_id]
