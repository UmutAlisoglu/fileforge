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
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .converters import CONVERTERS as CORE_CONVERTERS, Cancelled, ConversionError, executable
from .advanced_converters import ADVANCED_CONVERTERS
from .image_batch import convert_images
from .workspace import WORKSPACE, workspace_manifest

CONVERTERS = {**CORE_CONVERTERS, **ADVANCED_CONVERTERS, 'image': convert_images}
VERSION = '0.3.0'

STATIC = Path(__file__).parent / "static"
DATA = Path(os.environ.get("FILEFORGE_DATA_DIR", Path(tempfile.gettempdir()) / "fileforge-jobs"))
DATA.mkdir(parents=True, exist_ok=True)
RETENTION = 24 * 60 * 60
EXTENSIONS = {
    "video": {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"},
    "spreadsheet": {".xlsx", ".csv"},
    "image": {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"},
    "merge": {".pdf"},
    "background": {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"},
    "trace": {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"},
    "crop": {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"},
    "pdfimages": {".pdf"}, "organize": {".pdf"}, "pdfpreview": {".pdf"},
}
LIMITS = {"video": 2_000_000_000, "spreadsheet": 50_000_000, "image": 100_000_000, "merge": 250_000_000,
          "background": 100_000_000, "trace": 100_000_000, "crop": 100_000_000,
          "pdfimages": 250_000_000, "organize": 250_000_000, "pdfpreview": 250_000_000}
MULTI_LIMIT = 500_000_000
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
                "download_url": f"/api/jobs/{self.id}/download" if self.status == "completed" else None,
                "preview_url": f"/api/jobs/{self.id}/preview" if self.status == "completed" and self.output and self.output.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.svg'} else None}


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
for folder in ('tools', 'vendor', 'fonts', 'licenses', 'icons', 'assets'):
    if (WORKSPACE / folder).is_dir():
        app.mount('/' + folder, StaticFiles(directory=WORKSPACE / folder, html=True), name='workspace-' + folder)


@app.middleware("http")
async def local_origin(request: Request, call_next):
    if request.method in {"POST", "DELETE", "PUT", "PATCH"}:
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
            return JSONResponse({"detail": "Open FileForge from its local address to use the tools."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    workspace_page = request.url.path.startswith(('/tools/', '/vendor/', '/assets/', '/fonts/', '/licenses/'))
    if workspace_page:
        # libheif's Embind bindings generate functions inside the isolated
        # finish worker. Keep that permission out of every page and other engine.
        script_policy = "'self' 'wasm-unsafe-eval'"
        if request.url.path.startswith('/tools/_assets/finish.worker-'):
            script_policy += " 'unsafe-eval'"
        response.headers['Content-Security-Policy'] = (
            f"default-src 'self'; script-src {script_policy}; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' blob: data:; font-src 'self' data:; connect-src 'self' blob:; "
            "worker-src 'self' blob:; frame-src 'self' blob:; media-src 'self' blob: data:; "
            "object-src 'none'; frame-ancestors 'self'; form-action 'self'; base-uri 'self'"
        )
    else:
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; "
            "connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
        )
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
    response.headers['Cross-Origin-Embedder-Policy'] = 'require-corp'
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
    return response


@app.get("/")
def index():
    if workspace_manifest():
        return RedirectResponse('/tools/workspace/', status_code=307)
    return FileResponse(STATIC / "index.html")


@app.get('/native/')
def native_tools():
    return FileResponse(STATIC / 'index.html')


@app.get('/desktop-help/')
def desktop_help():
    return FileResponse(STATIC / 'desktop-help.html')


@app.get('/workspace-notices')
def workspace_notices():
    if not workspace_manifest():
        raise HTTPException(404, 'Prepare the desktop workspace first.')
    return FileResponse(WORKSPACE / 'THIRD_PARTY_NOTICES.md', media_type='text/plain')


@app.get('/workspace-source')
def workspace_source():
    if not workspace_manifest():
        raise HTTPException(404, 'Prepare the desktop workspace first.')
    return FileResponse(WORKSPACE / 'SOURCE.md', media_type='text/plain')


@app.get("/api/health")
def health():
    return {"status": "ok", "version": VERSION, "tools": [tool for tool in CONVERTERS if tool != 'pdfpreview'], "video_available": bool(executable("ffmpeg") and executable("ffprobe")),
            "max_file_bytes": LIMITS, "retention_hours": 24,
            "workspace": {key: value for key, value in (workspace_manifest() or {}).items() if key != 'files'}}


def validate_options(tool, raw):
    try:
        if len(raw) > 50_000:
            raise ValueError()
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
        if tool == 'background':
            fill = options.get('fill', 'transparent')
            if fill not in {'transparent', 'white'}:
                raise ValueError()
            return {'fill': fill}
        if tool == 'trace':
            precision = options.get('precision', 4)
            detail = options.get('detail', 'balanced')
            if type(precision) is not int or not 1 <= precision <= 8 or detail not in {'simple', 'balanced', 'fine'}:
                raise ValueError()
            return {'precision': precision, 'detail': detail}
        if tool == 'crop':
            rectangle = {key: options.get(key) for key in ('x', 'y', 'width', 'height')}
            if any(type(value) is not int for value in rectangle.values()):
                raise ValueError()
            if any(not 0 <= rectangle[key] <= 40000 for key in ('x', 'y')) or any(not 1 <= rectangle[key] <= 40000 for key in ('width', 'height')):
                raise ValueError()
            output_format = options.get('format', 'png')
            if output_format not in {'png', 'jpg', 'webp'}:
                raise ValueError()
            return {**rectangle, 'format': output_format}
        if tool == 'pdfimages':
            pages = options.get('pages', '')
            edge = options.get('edge', 2400)
            output_format = options.get('format', 'png')
            if not isinstance(pages, str) or len(pages) > 500 or type(edge) is not int or edge not in {1200, 2400, 3600} or output_format not in {'png', 'jpg'}:
                raise ValueError()
            return {'pages': pages, 'edge': edge, 'format': output_format}
        if tool == 'organize':
            pages = options.get('pages')
            if not isinstance(pages, list) or not 1 <= len(pages) <= 200:
                raise ValueError()
            plan = []
            for page in pages:
                if not isinstance(page, dict):
                    raise ValueError()
                values = {key: page.get(key) for key in ('file_index', 'page_index', 'rotation')}
                if any(type(value) is not int for value in values.values()) or not 0 <= values['file_index'] < 20 or not 0 <= values['page_index'] < 2500 or values['rotation'] not in {0, 90, 180, 270}:
                    raise ValueError()
                plan.append(values)
            return {'pages': plan}
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
    minimum, maximum = (2, 20) if tool == 'merge' else (1, 20) if tool in {'organize', 'pdfpreview'} else (1, 50) if tool == 'image' else (1, 1)
    if not minimum <= len(files) <= maximum:
        raise HTTPException(400, f'Select {minimum}-{maximum} files for this tool.')
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
                    if maximum > 1 and job.input_size + size > MULTI_LIMIT:
                        raise HTTPException(413, 'Keep the selection under 500 MB total.')
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


@app.get('/api/jobs/{identifier}/preview')
def preview_output(identifier: str):
    job = find_job(identifier)
    types = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml'}
    if job.status != 'completed' or not job.output or job.output.suffix.lower() not in types:
        raise HTTPException(409, 'This result has no image preview.')
    return FileResponse(job.output, media_type=types[job.output.suffix.lower()])


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
