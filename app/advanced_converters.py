"""Local image and PDF engines for the desktop toolbox.

The model and native runtimes ship with FileForge. These engines neither contact
an external service nor execute PDF actions, embedded scripts, or links.
"""
from __future__ import annotations

import base64
import io
import json
import math
import multiprocessing
import re
import threading
import time
import warnings
import zipfile
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter

from .converters import Cancelled, ConversionError, checkpoint, update


MODEL = Path(__file__).parent / "models" / "u2netp.onnx"
# PDFium cannot be called concurrently, even for unrelated documents. Native
# rendering is serialized; the other engine in the job pool can still work.
PDFIUM_LOCK = threading.Lock()
MAX_PDF_OUTPUT = 500_000_000


def _stem(job, index=0):
    return Path(job.filenames[index]).stem or "file"


def _image(job, maximum):
    checkpoint(job)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(job.sources[0]) as opened:
                if opened.width * opened.height > maximum:
                    raise ConversionError(f"Choose an image below {maximum // 1_000_000} megapixels.")
                if getattr(opened, "n_frames", 1) > 1:
                    job.warnings.append("Only the first frame of this animated image was used.")
                # Crop coordinates describe the upright image shown in the UI.
                oriented = ImageOps.exif_transpose(opened)
                try:
                    result = oriented.convert("RGBA")
                    result.info.clear()
                    return result
                finally:
                    oriented.close()
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ConversionError("This image is too large to process. Resize it first.") from exc


def _save_image(image, output, output_format):
    if output_format == "jpg":
        rgba = image.convert("RGBA")
        try:
            with Image.new("RGB", image.size, "white") as flattened:
                flattened.paste(rgba, mask=rgba.getchannel("A"))
                flattened.save(output, "JPEG", quality=92)
        finally:
            rgba.close()
    else:
        image.info.clear()
        image.save(output, {"png": "PNG", "webp": "WEBP"}[output_format],
                   **({"quality": 92} if output_format == "webp" else {}))


def crop_image(job):
    update(job, 10, "Reading the upright image")
    with _image(job, 40_000_000) as image:
        values = [job.options.get(key) for key in ("x", "y", "width", "height")]
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise ConversionError("Enter whole pixel values for the crop.")
        x, y, width, height = values
        if x < 0 or y < 0 or width < 1 or height < 1 or x + width > image.width or y + height > image.height:
            raise ConversionError("Keep the crop inside the upright image.")
        output_format = job.options.get("format", "png")
        if output_format not in {"png", "jpg", "webp"}:
            raise ConversionError("Choose PNG, JPG, or WebP output.")
        checkpoint(job)
        output = job.directory / f"{_stem(job)}-cropped.{output_format}"
        update(job, 65, "Exporting the selected area")
        with image.crop((x, y, x + width, y + height)) as cropped:
            _save_image(cropped, output, output_format)
        checkpoint(job)
        return output


def _model_prediction(job, tensor):
    import onnxruntime as ort

    if not MODEL.is_file():
        raise ConversionError("The background model is missing. Reinstall the complete FileForge package.")
    update(job, 20, "Preparing the bundled background model")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.log_severity_level = 3
    session = ort.InferenceSession(str(MODEL), sess_options=options, providers=["CPUExecutionProvider"])
    checkpoint(job)
    run_options = ort.RunOptions()
    finished = threading.Event()

    def monitor():
        while not finished.wait(0.05):
            if job.cancel.is_set():
                # ONNX Runtime checks this flag inside the active native run.
                run_options.terminate = True
                return

    watcher = threading.Thread(target=monitor, daemon=True, name="fileforge-model-cancel")
    watcher.start()
    try:
        update(job, 35, "Finding the subject on your device")
        try:
            prediction = session.run([session.get_outputs()[0].name],
                                     {session.get_inputs()[0].name: tensor}, run_options=run_options)[0]
        except Exception:
            checkpoint(job)
            raise
        checkpoint(job)
        return prediction
    finally:
        finished.set()
        watcher.join(timeout=1)


def remove_background(job):
    import numpy as np

    fill = job.options.get("fill", "transparent")
    if fill not in {"transparent", "white"}:
        raise ConversionError("Choose a transparent or white background.")
    update(job, 5, "Reading image")
    with _image(job, 20_000_000) as image:
        # White inference background avoids treating transparent RGB values as
        # black objects. Original alpha is combined with the predicted mask.
        with Image.new("RGB", image.size, "white") as inference_image:
            inference_image.paste(image, mask=image.getchannel("A"))
            with inference_image.resize((320, 320), Image.Resampling.BILINEAR) as small:
                pixels = np.asarray(small, dtype=np.float32)
        maximum = max(1.0, float(pixels.max()))
        mean = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)
        deviation = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)
        tensor = np.ascontiguousarray(((pixels / maximum - mean) / deviation).transpose(2, 0, 1)[None])
        prediction = _model_prediction(job, tensor).reshape(-1)
        low, high = float(prediction.min()), float(prediction.max())
        if prediction.size != 320 * 320 or not math.isfinite(low) or not math.isfinite(high) or high - low < 0.00001:
            raise ConversionError("No clear subject was found. Try a photo with a distinct foreground object.")
        checkpoint(job)
        update(job, 75, "Applying the foreground mask")
        mask_values = np.clip((prediction - low) / (high - low) * 255, 0, 255).round().astype(np.uint8).reshape(320, 320)
        with Image.fromarray(mask_values) as small_mask:
            with small_mask.resize(image.size, Image.Resampling.BILINEAR) as mask:
                alpha = np.asarray(image.getchannel("A"), dtype=np.uint16)
                combined = (alpha * np.asarray(mask, dtype=np.uint16) + 127) // 255
                with Image.fromarray(combined.astype(np.uint8)) as source_alpha:
                    image.putalpha(source_alpha)
        output = job.directory / f"{_stem(job)}-background-removed.png"
        update(job, 90, "Writing your PNG")
        if fill == "white":
            with Image.new("RGBA", image.size, "white") as canvas:
                canvas.alpha_composite(image)
                canvas.save(output, "PNG")
        else:
            image.save(output, "PNG")
        checkpoint(job)
        job.warnings.append("Review fine hair, translucent areas, and edges before using the result.")
        return output


def _trace_process(source, output, precision, detail, result):
    """Native tracing runs separately so cancellation can stop it immediately."""
    try:
        import vtracer

        filter_speckle, length_threshold, corner_threshold, layer_difference = {
            "simple": (16, 6.0, 90, 32), "balanced": (4, 4.0, 60, 16), "fine": (2, 2.0, 45, 8),
        }[detail]
        # The ABI3 Windows wheel's keyword parser crashes on Python 3.14.
        # Positional arguments work and are verified by real vector exports.
        vtracer.convert_image_to_svg_py(source, output, "color", "stacked", "spline",
                                       filter_speckle, precision, layer_difference,
                                       corner_threshold, length_threshold, 10, 45, 3)
        result.send(None)
    except Exception:
        result.send("The tracing engine could not process this image. Try simpler detail or another image.")
    finally:
        result.close()


def trace_image(job):

    precision = job.options.get("precision", 4)
    detail = job.options.get("detail", "balanced")
    if isinstance(precision, bool) or not isinstance(precision, int) or not 1 <= precision <= 8 or detail not in {"simple", "balanced", "fine"}:
        raise ConversionError("Choose a colour precision from 1 to 8 and a supported detail level.")
    update(job, 10, "Preparing image shapes and colours")
    with _image(job, 40_000_000) as image:
        original_size = image.size
        image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
        if image.size != original_size:
            job.warnings.append(f"Tracing was scaled to {image.width} × {image.height} pixels to keep the SVG manageable.")
        prepared = job.directory / "trace-input.png"
        image.save(prepared, "PNG")
    checkpoint(job)
    output = job.directory / f"{_stem(job)}-traced.svg"
    update(job, 35, "Tracing editable vector paths")
    context = multiprocessing.get_context("spawn")
    received, sent = context.Pipe(duplex=False)
    process = context.Process(target=_trace_process, args=(str(prepared), str(output), precision, detail, sent),
                              name="fileforge-trace", daemon=True)
    started = False
    try:
        process.start()
        started = True
        sent.close()
        began = time.monotonic()
        while process.is_alive():
            checkpoint(job)
            if time.monotonic() - began > 300:
                raise ConversionError("Tracing exceeded five minutes. Choose simpler detail or a smaller image.")
            job.cancel.wait(0.05)
        process.join(timeout=5)
        checkpoint(job)
        if process.exitcode != 0 or not output.is_file():
            raise ConversionError("The tracing engine stopped. Try simpler detail or another image.")
        if received.poll():
            try:
                message = received.recv()
            except EOFError:
                message = None
            if message:
                raise ConversionError(message)
        if output.stat().st_size > 50_000_000:
            raise ConversionError("This SVG exceeds 50 MB. Try simpler detail or lower colour precision.")
        job.warnings.append("Photographs are approximated as vector shapes; logos and simple artwork usually trace best.")
        return output
    finally:
        if started:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            process.close()
        sent.close()
        received.close()
        prepared.unlink(missing_ok=True)


def parse_pages(value, total, maximum=100):
    """Return unique zero-based page numbers in the requested order."""
    if not isinstance(value, str) or len(value) > 2000:
        raise ConversionError("Enter page numbers such as 1, 3-5, or all.")
    if value.strip().lower() in {"", "all"}:
        result = list(range(total))
    else:
        result, seen = [], set()
        for part in value.split(","):
            match = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+)\s*)?", part)
            if not match:
                raise ConversionError("Enter page numbers such as 1, 3-5, or all.")
            start = int(match[1])
            end = int(match[2] or match[1])
            if start < 1 or end < start or end > total:
                raise ConversionError(f"Choose pages between 1 and {total}, with ascending ranges.")
            if end - start + 1 > maximum:
                raise ConversionError(f"Export at most {maximum} pages at a time.")
            for page in range(start - 1, end):
                if page not in seen:
                    result.append(page)
                    seen.add(page)
                    if len(result) > maximum:
                        raise ConversionError(f"Export at most {maximum} pages at a time.")
    if not result or len(result) > maximum:
        raise ConversionError(f"Export between 1 and {maximum} pages at a time.")
    return result


def _read_pdfs(job, maximum=200):
    if not 1 <= len(job.sources) <= 20:
        raise ConversionError("Choose between 1 and 20 PDFs.")
    readers, count = [], 0
    for index, source in enumerate(job.sources):
        checkpoint(job)
        reader = PdfReader(source)
        if reader.is_encrypted:
            raise ConversionError(f"{job.filenames[index]} is password protected. Use an unlocked copy.")
        if not len(reader.pages):
            raise ConversionError(f"{job.filenames[index]} contains no pages.")
        count += len(reader.pages)
        if count > maximum:
            raise ConversionError(f"Choose PDFs with at most {maximum} pages in total.")
        readers.append(reader)
    return readers


@contextmanager
def _pdfium_access(job):
    while not PDFIUM_LOCK.acquire(timeout=0.1):
        checkpoint(job)
    try:
        checkpoint(job)
        yield
    finally:
        PDFIUM_LOCK.release()


def _render_page(page, edge):
    width, height = page.get_size()
    if not all(math.isfinite(number) and number > 0 for number in (width, height)):
        raise ConversionError("This PDF contains an invalid page size.")
    bitmap = page.render(scale=edge / max(width, height), may_draw_forms=False,
                         fill_color=(255, 255, 255, 255))
    try:
        # to_pil can share native memory; copy before releasing PDFium's bitmap.
        rendered = bitmap.to_pil().copy()
        return rendered, width, height
    finally:
        bitmap.close()


def pdf_images(job):
    import pypdfium2 as pdfium

    edge = job.options.get("edge", 2400)
    output_format = job.options.get("format", "png")
    if edge not in {1200, 2400, 3600} or output_format not in {"png", "jpg"}:
        raise ConversionError("Choose a supported image size and PNG or JPG output.")
    update(job, 5, "Reading PDF pages")
    readers = _read_pdfs(job, maximum=5000)
    if len(readers) != 1:
        raise ConversionError("Choose one PDF to export as images.")
    pages = parse_pages(job.options.get("pages", "all"), len(readers[0].pages))
    output = job.directory / (f"{_stem(job)}-page-{pages[0] + 1:04d}.{output_format}" if len(pages) == 1
                              else f"{_stem(job)}-pages.zip")
    total_bytes = 0
    archive = zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) if len(pages) > 1 else None
    try:
        with _pdfium_access(job):
            with pdfium.PdfDocument(str(job.sources[0])) as document:
                for position, page_index in enumerate(pages):
                    update(job, 10 + 80 * position / len(pages), f"Rendering page {page_index + 1}")
                    page = document[page_index]
                    try:
                        image, _, _ = _render_page(page, edge)
                    finally:
                        page.close()
                    try:
                        buffer = io.BytesIO()
                        _save_image(image, buffer, output_format)
                        content = buffer.getvalue()
                    finally:
                        image.close()
                    checkpoint(job)
                    total_bytes += len(content)
                    if total_bytes > MAX_PDF_OUTPUT:
                        raise ConversionError("The exported images exceed 500 MB. Select fewer pages or a smaller image size.")
                    if archive:
                        archive.writestr(f"{_stem(job)}-page-{page_index + 1:04d}.{output_format}", content)
                    else:
                        output.write_bytes(content)
        job.warnings.append("Pages are rendered as pictures; embedded scripts, links, and interactive forms are not run.")
        return output
    finally:
        if archive:
            archive.close()


def pdf_preview(job):
    import pypdfium2 as pdfium

    update(job, 5, "Reading PDF page counts")
    readers = _read_pdfs(job)
    total = sum(len(reader.pages) for reader in readers)
    cards = []
    with _pdfium_access(job):
        for file_index, source in enumerate(job.sources):
            with pdfium.PdfDocument(str(source)) as document:
                for page_index in range(len(document)):
                    update(job, 10 + 85 * len(cards) / total, f"Preparing page {len(cards) + 1} of {total}")
                    page = document[page_index]
                    try:
                        image, width, height = _render_page(page, 240)
                    finally:
                        page.close()
                    try:
                        buffer = io.BytesIO()
                        image.save(buffer, "PNG")
                    finally:
                        image.close()
                    checkpoint(job)
                    cards.append({"file_index": file_index, "page_index": page_index,
                                  "name": job.filenames[file_index], "rotation": 0, "selected": True,
                                  "width": width, "height": height,
                                  "thumbnail": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")})
    output = job.directory / "page-previews.json"
    output.write_text(json.dumps({"pages": cards, "file_count": len(job.sources)}, ensure_ascii=False), encoding="utf-8")
    return output


def organize_pdf(job):
    update(job, 5, "Reading your PDFs")
    readers = _read_pdfs(job)
    selections = job.options.get("pages")
    if not isinstance(selections, list) or not 1 <= len(selections) <= 200:
        raise ConversionError("Select between 1 and 200 pages to export.")
    output = job.directory / "organized.pdf"
    writer = PdfWriter()
    try:
        for position, selection in enumerate(selections):
            if not isinstance(selection, dict):
                raise ConversionError("Choose valid PDF pages.")
            file_index, page_index, rotation = (selection.get(key) for key in ("file_index", "page_index", "rotation"))
            if any(isinstance(value, bool) or not isinstance(value, int) for value in (file_index, page_index, rotation)):
                raise ConversionError("Choose valid PDF pages and quarter-turn rotations.")
            if not 0 <= file_index < len(readers) or not 0 <= page_index < len(readers[file_index].pages) or rotation not in {0, 90, 180, 270}:
                raise ConversionError("The selected PDF page or rotation is invalid. Refresh the page previews.")
            update(job, 10 + 80 * position / len(selections), f"Adding page {position + 1} of {len(selections)}")
            # Each occurrence gets its own page object so rotating a duplicated
            # page cannot change another occurrence or the source reader.
            writer.reset_translation(readers[file_index])
            page = writer.add_page(readers[file_index].pages[page_index])
            if rotation:
                page.rotate(rotation)
        update(job, 95, "Writing the arranged PDF")
        with output.open("wb") as stream:
            writer.write(stream)
        checkpoint(job)
        job.warnings.append("Review the export before replacing an original. Digital signatures and interactive forms may not survive page rearrangement.")
        return output
    finally:
        writer.close()


ADVANCED_CONVERTERS = {"background": remove_background, "trace": trace_image, "crop": crop_image,
                       "pdfimages": pdf_images, "organize": organize_pdf, "pdfpreview": pdf_preview}
