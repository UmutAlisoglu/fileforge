from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .converters import CONVERTERS, Cancelled, ConversionError, executable

STATIC = Path(__file__).parent / "static"
DATA = Path(os.environ.get("FILEFORGE_DATA_DIR", Path(tempfile.gettempdir()) / "fileforge-jobs"))
DATA.mkdir(parents=True, exist_ok=True)
RETENTION = 24 * 60 * 60
EXTENSIONS = {
    "video": {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"},
    "spreadsheet": {".xlsx", ".csv"},
    "image": {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"},
    "merge": {".pdf"},
}
LIMITS = {"video": 2_000_000_000, "spreadsheet": 50_000_000, "image": 100_000_000, "merge": 250_000_000}
TERMINAL = {"completed", "failed", "cancelled"}
jobs = {}
lock = threading.RLock()
pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="fileforge")


@dataclass
class Job:
    id: str
    tool: str
    options: dict
    directory: Path
    sources: list = field(default_factory=list)
    filenames: list = field(default_factory=list)
    input_size: int = 0
    status: str = "uploading"
    progress: int = 0
    stage: str = "Saving files"
    error: str | None = None
    output: Path | None = None
    warnings: list = field(default_factory=list)
    created: float = field(default_factory=time.time)
    finished: float | None = None
    cancel: threading.Event = field(default_factory=threading.Event)

    def public(self):
        return {"id": self.id, "tool": self.tool, "filenames": self.filenames,
                "status": self.status, "progress": self.progress, "stage": self.stage,
                "error": self.error, "warnings": self.warnings.copy(), "created": self.created,
                "input_size": self.input_size,
                "output_size": self.output.stat().st_size if self.output and self.output.exists() else None,
                "output_name": self.output.name if self.output else None,
                "download_url": f"/api/jobs/{self.id}/download" if self.status == "completed" else None}


def cleanup():
    with lock:
        for identifier, job in list(jobs.items()):
            if job.status in TERMINAL and job.finished and time.time() - job.finished > RETENTION:
                shutil.rmtree(job.directory, ignore_errors=True)
                del jobs[identifier]
    # Only our UUID-named directories. Active jobs are never removed.
    for directory in DATA.iterdir():
        if directory.is_dir() and re.fullmatch(r"[a-f0-9]{32}", directory.name):
            if directory.name not in jobs and time.time() - directory.stat().st_mtime > RETENTION:
                shutil.rmtree(directory, ignore_errors=True)


async def janitor():
    while True:
        await asyncio.sleep(60)
        cleanup()


@asynccontextmanager
async def lifespan(app):
    cleanup()
    task = asyncio.create_task(janitor())
    yield
    task.cancel()
    with lock:
        for job in jobs.values():
            if job.status not in TERMINAL:
                job.cancel.set()
    pool.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="FileForge", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def local_origin(request: Request, call_next):
    if request.method in {"POST", "DELETE", "PUT", "PATCH"}:
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
            return JSONResponse({"detail": "Open FileForge from its local address to use the tools."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; "
        "connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
    )
    return response


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "video_available": bool(executable("ffmpeg") and executable("ffprobe")),
            "max_file_bytes": LIMITS, "retention_hours": 24}


def validate_options(tool, raw):
    try:
        options = json.loads(raw)
        if not isinstance(options, dict):
            raise ValueError()
        if tool == "video":
            target = float(options.get("target_mb", 25))
            height = int(options.get("height", 720))
            remove_audio = options.get("remove_audio", False)
            if not math.isfinite(target) or not 0.1 <= target <= 10000 or height not in {0, 480, 720, 1080}:
                raise ValueError()
            if not isinstance(remove_audio, bool):
                raise ValueError()
            return {"target_mb": target, "height": height, "remove_audio": remove_audio}
        if tool == "image":
            output_format = options.get("format", "webp")
            quality = int(options.get("quality", 85))
            width = int(options.get("width", 0))
            if output_format not in {"jpg", "png", "webp", "pdf"} or not 1 <= quality <= 100 or not 0 <= width <= 12000:
                raise ValueError()
            return {"format": output_format, "quality": quality, "width": width}
        if tool == "spreadsheet":
            orientation = options.get("orientation", "landscape")
            if orientation not in {"portrait", "landscape"}:
                raise ValueError()
            return {"orientation": orientation}
        return {}
    except (ValueError, TypeError, OverflowError) as exc:
        raise HTTPException(400, "Invalid conversion settings.") from exc


def run_job(job):
    try:
        if job.cancel.is_set():
            raise Cancelled()
        job.status = "running"
        job.stage = "Starting conversion"
        job.output = CONVERTERS[job.tool](job)
        if job.cancel.is_set():
            raise Cancelled()
        job.progress = 100
        job.stage = "Ready to download"
        job.status = "completed"
    except Cancelled:
        job.status = "cancelled"
        job.stage = "Cancelled"
        job.output = None
    except ConversionError as exc:
        job.status = "failed"
        job.stage = "Conversion failed"
        job.error = str(exc)
        job.output = None
    except Exception:
        logging.exception("Conversion failed for job %s", job.id)
        job.status = "failed"
        job.stage = "Conversion failed"
        job.error = "This file could not be converted. Check that it opens correctly and is not password protected."
        job.output = None
    finally:
        job.finished = time.time()
        # Uploaded originals and encoder intermediates are no longer needed.
        with lock:
            if job.directory.exists():
                for path in job.directory.iterdir():
                    if path != job.output:
                        path.unlink(missing_ok=True)


@app.post("/api/jobs", status_code=202)
async def create_job(tool: str = Form(...), options: str = Form("{}"), files: list[UploadFile] = File(...)):
    if tool not in CONVERTERS:
        raise HTTPException(400, "Choose a supported conversion tool.")
    settings = validate_options(tool, options)
    if (tool != "merge" and len(files) != 1) or (tool == "merge" and not 2 <= len(files) <= 20):
        raise HTTPException(400, "Select 2-20 PDFs to merge, or one file for other tools.")
    with lock:
        if sum(job.status not in TERMINAL for job in jobs.values()) >= 8:
            raise HTTPException(429, "The queue is full. Wait for a conversion to finish.")
        identifier = uuid.uuid4().hex
        directory = DATA / identifier
        directory.mkdir()
        job = Job(identifier, tool, settings, directory)
        jobs[identifier] = job
    try:
        for index, upload in enumerate(files):
            original = (upload.filename or "file").replace("\\", "/").rsplit("/", 1)[-1]
            filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", original).strip(" .")[:180] or "file"
            suffix = Path(filename).suffix.lower()
            if suffix not in EXTENSIONS[tool]:
                raise HTTPException(400, f"Unsupported file type for this tool: {suffix or '(none)'}.")
            destination = directory / f"{index + 1}-{filename}"
            size = 0
            with destination.open("wb") as stream:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > LIMITS[tool]:
                        raise HTTPException(413, f"File exceeds this tool's {LIMITS[tool] / 1_000_000:g} MB limit.")
                    stream.write(chunk)
            if not size:
                raise HTTPException(400, "Empty files cannot be converted.")
            job.sources.append(destination)
            job.filenames.append(filename)
            job.input_size += size
        job.status = "queued"
        job.stage = "Waiting for a worker"
        pool.submit(run_job, job)
        return job.public()
    except BaseException:
        with lock:
            jobs.pop(identifier, None)
        shutil.rmtree(directory, ignore_errors=True)
        raise
    finally:
        for upload in files:
            await upload.close()


@app.get("/api/jobs")
def list_jobs():
    with lock:
        return [job.public() for job in sorted(jobs.values(), key=lambda item: item.created, reverse=True)
                if job.status != "uploading"]


def find_job(identifier):
    with lock:
        job = jobs.get(identifier)
    if not job:
        raise HTTPException(404, "This conversion has expired or was cleared.")
    return job


@app.get("/api/jobs/{identifier}")
def get_job(identifier: str):
    return find_job(identifier).public()


@app.get("/api/jobs/{identifier}/download")
def download(identifier: str):
    job = find_job(identifier)
    if job.status != "completed" or not job.output:
        raise HTTPException(409, "This conversion is not ready to download.")
    return FileResponse(job.output, filename=job.output.name, media_type="application/octet-stream")


@app.post("/api/jobs/{identifier}/cancel")
def cancel(identifier: str):
    job = find_job(identifier)
    if job.status not in TERMINAL:
        job.cancel.set()
    return {"status": "cancellation_requested" if job.status not in TERMINAL else job.status}


@app.delete("/api/jobs/{identifier}")
def delete(identifier: str):
    with lock:
        job = find_job(identifier)
        if job.status not in TERMINAL:
            raise HTTPException(409, "Cancel the conversion before removing it.")
        shutil.rmtree(job.directory, ignore_errors=True)
        del jobs[identifier]
    return {"status": "deleted"}
