"""FastAPI entry point. The web layer only orchestrates — pipeline logic lives in app/pipeline.

Run locally from the backend/ folder:
    .venv/bin/uvicorn app.main:app --reload

How processing works:
    1. POST /api/meetings      upload a recording -> quick file check -> returns a job id (202)
    2. (background)            the three stages run, updating the job's progress
    3. GET /api/meetings/{id}  poll every second or so until status is "done" or "failed"
"""

import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.config import ConfigError, Settings, get_settings
from app.jobs import Job, JobError, JobStore
from app.pipeline.audio import BYTES_PER_MB, probe_audio_duration, validate_audio_file
from app.pipeline.errors import STAGE_FILE_CHECK, PipelineError
from app.pipeline.run import PipelineClients, run_pipeline

logger = logging.getLogger("app")

app = FastAPI(title="AI Meeting Assistant")

# Allow the Vite dev server (the frontend) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CHUNK_SIZE = 1024 * 1024
FORM_OVERHEAD_BYTES = 1024 * 1024  # room for the form fields around the file itself

GENERIC_ERROR = JobError(
    stage=None,
    message="Something went wrong on the server while processing the recording.",
    fix="Try again. If it keeps happening, check the server log.",
)

job_store = JobStore()


# --- Dependencies (tests replace these with fakes) ---


def get_clients(settings: Annotated[Settings, Depends(get_settings)]) -> PipelineClients:
    return PipelineClients.from_settings(settings)


def get_job_store() -> JobStore:
    return job_store


# --- Errors: always {"error": {"stage", "message", "fix"}} in plain English ---


def error_response(status_code: int, error: JobError) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": error.model_dump()})


def pipeline_error_to_job_error(error: PipelineError) -> JobError:
    return JobError(stage=error.stage, message=f"{error.stage} failed: {error.problem}.", fix=error.fix)


@app.exception_handler(PipelineError)
def handle_pipeline_error(request: Request, error: PipelineError) -> JSONResponse:
    status = 400 if error.stage == STAGE_FILE_CHECK else 502  # bad upload vs. an AI service failed
    return error_response(status, pipeline_error_to_job_error(error))


@app.exception_handler(ConfigError)
def handle_config_error(request: Request, error: ConfigError) -> JSONResponse:
    return error_response(500, JobError(stage=None, message=str(error), fix=None))


@app.exception_handler(RequestValidationError)
def handle_bad_request(request: Request, error: RequestValidationError) -> JSONResponse:
    return error_response(400, JobError(
        stage=None,
        message="The request was not in the expected format.",
        fix="Upload the recording as a form field named 'file'.",
    ))


@app.exception_handler(Exception)
def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
    logger.exception("Unexpected error handling %s %s", request.method, request.url.path)
    return error_response(500, GENERIC_ERROR)


@app.middleware("http")
async def reject_oversized_uploads(request: Request, call_next: Any) -> Any:
    """Refuse a too-large upload from its Content-Length header, before receiving the whole file."""
    if request.method == "POST" and request.url.path == "/api/meetings":
        try:
            # Look up get_settings through dependency_overrides so tests can use fake settings.
            settings = request.app.dependency_overrides.get(get_settings, get_settings)()
            limit = settings.max_upload_mb * BYTES_PER_MB + FORM_OVERHEAD_BYTES
            if int(request.headers.get("content-length", 0)) > limit:
                return too_large_response(settings.max_upload_mb)
        except (ConfigError, ValueError):
            pass  # the endpoint will report the configuration problem properly
    return await call_next(request)


def too_large_response(max_upload_mb: int) -> JSONResponse:
    return error_response(413, JobError(
        stage=STAGE_FILE_CHECK,
        message=f"{STAGE_FILE_CHECK} failed: the file is above the {max_upload_mb} MB limit.",
        fix="Upload a shorter or more compressed recording.",
    ))


# --- Endpoints ---


@app.get("/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, object]:
    """Confirm the server is running and show which models are configured (never keys)."""
    return {
        "status": "ok",
        "models": {
            "stt": settings.stt_model,
            "refiner": settings.refiner_model,
            "documenter": settings.documenter_model,
        },
    }


@app.post("/api/meetings", status_code=202, response_model=None)
def create_meeting(
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
    clients: Annotated[PipelineClients, Depends(get_clients)],
    jobs: Annotated[JobStore, Depends(get_job_store)],
    file: Annotated[UploadFile | None, File()] = None,
    glossary: Annotated[str, Form()] = "",
) -> Job | JSONResponse:
    """Upload a recording. Bad files are rejected right away; good ones start a background job."""
    if file is None or not file.filename:
        return error_response(400, JobError(
            stage=STAGE_FILE_CHECK,
            message=f"{STAGE_FILE_CHECK} failed: no file was uploaded.",
            fix="Choose an audio recording and try again.",
        ))

    work_dir = Path(tempfile.mkdtemp(prefix="meeting_"))
    try:
        audio_path = work_dir / safe_filename(file.filename)
        if not save_upload(file, audio_path, settings.max_upload_mb):
            shutil.rmtree(work_dir, ignore_errors=True)
            return too_large_response(settings.max_upload_mb)
        validate_audio_file(audio_path, settings.max_upload_mb, settings.max_audio_minutes)  # quick checks
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise

    job = jobs.create(filename=file.filename)
    terms = [term.strip() for term in glossary.split(",") if term.strip()]
    background_tasks.add_task(process_meeting, job.job_id, audio_path, work_dir, settings, clients, terms, jobs)
    return job


@app.get("/api/meetings/{job_id}", response_model=None)
def get_meeting(job_id: str, jobs: Annotated[JobStore, Depends(get_job_store)]) -> Job | JSONResponse:
    """Progress of a job, and its result once status is "done"."""
    job = jobs.get(job_id)
    if job is None:
        return error_response(404, JobError(
            stage=None,
            message="This processing job was not found. It may have expired or the server may have restarted.",
            fix="Upload the recording again.",
        ))
    return job


# Sample recordings for the "Try one of ours" buttons (files in the repo's samples/ folder).
SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples"
SAMPLES = {
    "technical_meeting": ("Model review", "recording.m4a"),
    "speakers_meeting": ("Release sync", "recording.m4a"),
    "meeting": ("Sprint planning", "recording.mp3"),
}


@app.get("/api/samples")
def list_samples() -> list[dict[str, object]]:
    """Sample meetings that exist on disk, with their length in seconds."""
    samples = []
    for sample_id, (title, filename) in SAMPLES.items():
        path = SAMPLES_DIR / sample_id / filename
        if path.is_file():
            samples.append({"id": sample_id, "title": title, "filename": f"{title.lower().replace(' ', '-')}{path.suffix}",
                            "seconds": round(probe_audio_duration(path) or 0)})
    return samples


@app.get("/api/samples/{sample_id}/audio", response_model=None)
def sample_audio(sample_id: str) -> FileResponse | JSONResponse:
    """The audio file of one sample (the browser then uploads it like any other recording)."""
    if sample_id not in SAMPLES or not (SAMPLES_DIR / sample_id / SAMPLES[sample_id][1]).is_file():
        return error_response(404, JobError(stage=None, message="That sample recording was not found.", fix="Choose another sample."))
    return FileResponse(SAMPLES_DIR / sample_id / SAMPLES[sample_id][1])


# --- Helpers ---


def process_meeting(
    job_id: str, audio_path: Path, work_dir: Path, settings: Settings,
    clients: PipelineClients, glossary: list[str], jobs: JobStore,
) -> None:
    """Runs in the background after the upload response is sent."""
    try:
        result = run_pipeline(
            audio_path, settings, clients, glossary,
            on_progress=lambda stage, state, seconds: jobs.update_stage(job_id, stage, state, seconds),
            on_note=lambda stage, note: jobs.set_note(job_id, stage, note),
            on_detail=lambda stage, detail: jobs.set_detail(job_id, stage, detail),
            on_refined=lambda refined: jobs.set_preview(job_id, refined),
        )
        jobs.finish(job_id, result)
    except PipelineError as error:
        jobs.fail(job_id, pipeline_error_to_job_error(error))
    except Exception:
        logger.exception("Job %s crashed", job_id)
        jobs.fail(job_id, GENERIC_ERROR)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def save_upload(upload: UploadFile, destination: Path, max_upload_mb: int) -> bool:
    """Copy the upload to disk in chunks. Returns False (and stops) if it passes the size limit."""
    limit = max_upload_mb * BYTES_PER_MB
    written = 0
    with destination.open("wb") as out:
        while chunk := upload.file.read(CHUNK_SIZE):
            written += len(chunk)
            if written > limit:
                return False
            out.write(chunk)
    return True


def safe_filename(filename: str) -> str:
    """Keep only the base name and safe characters: "../a b?.MP3" -> "a_b_.MP3"."""
    name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name).lstrip(".")
    return name[-100:] or "upload"
