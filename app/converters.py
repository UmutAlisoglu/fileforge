"""Conversion engines. Add a converter to CONVERTERS to extend the application."""
from __future__ import annotations

import csv
import json
import math
import os
import shutil
import subprocess
import time
import warnings
import zipfile
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageOps
from openpyxl import load_workbook
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle

Image.MAX_IMAGE_PIXELS = 40_000_000


class ConversionError(Exception):
    pass


class Cancelled(Exception):
    pass


def checkpoint(job):
    if job.cancel.is_set():
        raise Cancelled()


def update(job, progress, stage):
    checkpoint(job)
    job.progress = max(job.progress, min(99, int(progress)))
    job.stage = stage


def executable(name):
    configured = os.environ.get(f"FILEFORGE_{name.upper()}")
    return configured if configured and Path(configured).is_file() else shutil.which(name)


def media_info(path):
    probe = executable("ffprobe")
    if not probe:
        raise ConversionError("FFmpeg and FFprobe must be installed to use video tools.")
    try:
        result = subprocess.run(
            [probe, "-v", "error", "-protocol_whitelist", "file,pipe", "-show_format",
             "-show_streams", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30, creationflags=_creation_flags(),
        )
        if result.returncode:
            raise ConversionError("This file could not be read as a video.")
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired as exc:
        raise ConversionError("Video inspection timed out.") from exc


def _creation_flags():
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def run_encoder(command, job, duration, start, span):
    progress_path = job.directory / "encoder-progress.txt"
    progress_path.unlink(missing_ok=True)
    command = command[:1] + ["-progress", str(progress_path), "-nostats"] + command[1:]
    log_path = job.directory / "encoder.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log,
                                   creationflags=_creation_flags())
        started = time.monotonic()
        try:
            while process.poll() is None:
                checkpoint(job)
                if time.monotonic() - started > 7200:
                    raise ConversionError("Encoding exceeded the two-hour limit.")
                try:
                    lines = progress_path.read_text(errors="ignore").splitlines()
                    timestamps = [int(line.split("=", 1)[1]) for line in lines
                                  if line.startswith("out_time_us=") and line.split("=", 1)[1].isdigit()]
                    if timestamps:
                        update(job, start + span * min(1, timestamps[-1] / 1_000_000 / duration), job.stage)
                except OSError:
                    pass
                job.cancel.wait(0.2)
            checkpoint(job)
            if process.returncode:
                raise ConversionError("FFmpeg could not encode this video. Try another source file or a larger target.")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)


def compress_video(job):
    binary = executable("ffmpeg")
    if not binary:
        raise ConversionError("Install FFmpeg to use video compression.")
    source = job.sources[0]
    info = media_info(source)
    video = next((stream for stream in info.get("streams", []) if stream["codec_type"] == "video"
                  and not stream.get("disposition", {}).get("attached_pic")), None)
    if not video:
        raise ConversionError("The file does not contain a video track.")
    try:
        duration = float(info["format"].get("duration") or video.get("duration") or 0)
    except (ValueError, KeyError):
        duration = 0
    if not math.isfinite(duration) or duration <= 0:
        raise ConversionError("The video duration could not be determined.")
    target = int(job.options["target_mb"] * 1_000_000)
    audio = not job.options["remove_audio"] and any(stream["codec_type"] == "audio" for stream in info["streams"])
    audio_kbps = 64 if audio else 0
    video_kbps = int(target * 0.92 * 8 / duration / 1000 - audio_kbps)
    if video_kbps < 35:
        minimum = (35 + audio_kbps) * duration * 1000 / 8 / 0.92 / 1_000_000
        raise ConversionError(f"Target too small for this duration. Try at least {minimum:.1f} MB or remove audio.")
    height = job.options["height"]
    video_filter = (f"scale=-2:trunc(min(ih\\,{height})/2)*2" if height
                    else "scale=trunc(iw/2)*2:trunc(ih/2)*2")
    output = job.directory / f"{Path(job.filenames[0]).stem}-compressed.mp4"
    for attempt in range(3):
        checkpoint(job)
        prefix = job.directory / f"pass-{attempt}"
        base = [binary, "-hide_banner", "-loglevel", "error", "-y", "-protocol_whitelist", "file,pipe",
                "-i", str(source), "-map", f"0:{video['index']}", "-c:v", "libx264",
                "-preset", "medium", "-threads", "2", "-b:v", f"{video_kbps}k",
                "-pix_fmt", "yuv420p", "-vf", video_filter, "-t", str(duration),
                "-passlogfile", str(prefix)]
        update(job, 5, "Analyzing video" if attempt == 0 else "Refining file size")
        run_encoder(base + ["-pass", "1", "-an", "-f", "null", os.devnull],
                    job, duration, 5, 35)
        update(job, 40, "Encoding MP4" if attempt == 0 else "Refining file size")
        audio_args = ["-map", "0:a:0?", "-c:a", "aac", "-b:a", f"{audio_kbps}k"] if audio else ["-an"]
        run_encoder(base + ["-pass", "2"] + audio_args + ["-movflags", "+faststart", str(output)],
                    job, duration, 40, 55)
        if output.stat().st_size <= target:
            job.warnings.append("Lower target sizes can reduce picture quality.")
            return output
        video_kbps = int(video_kbps * target / output.stat().st_size * 0.90)
        if video_kbps < 35:
            break
    raise ConversionError("The finished file exceeded the target. Increase the target size and try again.")


def convert_image(job):
    source = job.sources[0]
    output_format = job.options["format"]
    output = job.directory / f"{Path(job.filenames[0]).stem}-converted.{output_format}"
    update(job, 10, "Reading image")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(source) as opened:
            if getattr(opened, "n_frames", 1) > 1:
                job.warnings.append("Only the first frame of this animated image was converted.")
            image = ImageOps.exif_transpose(opened).copy()
    checkpoint(job)
    width = job.options["width"]
    if width and image.width > width:
        image.thumbnail((width, max(1, round(image.height * width / image.width))), Image.Resampling.LANCZOS)
    if output_format in {"jpg", "pdf"}:
        rgba = image.convert("RGBA")
        image = Image.new("RGB", rgba.size, "white")
        image.paste(rgba, mask=rgba.getchannel("A"))
    elif image.mode not in {"RGB", "RGBA"}:
        image = image.convert("RGBA")
    # Saving without metadata also removes embedded EXIF, including location data.
    image.info.clear()
    update(job, 65, "Writing image")
    options = {"quality": job.options["quality"]} if output_format in {"jpg", "webp"} else {}
    image.save(output, format={"jpg": "JPEG", "png": "PNG", "webp": "WEBP", "pdf": "PDF"}[output_format],
               **options)
    return output


def merge_pdf(job):
    output = job.directory / "merged.pdf"
    writer = PdfWriter()
    count = 0
    try:
        for index, source in enumerate(job.sources):
            checkpoint(job)
            reader = PdfReader(source)
            if reader.is_encrypted:
                raise ConversionError(f"{source.name} is password protected. Use an unlocked copy.")
            count += len(reader.pages)
            if count > 2500:
                raise ConversionError("This merge exceeds the 2,500-page limit.")
            for page in reader.pages:
                checkpoint(job)
                writer.add_page(page)
            update(job, 10 + 75 * (index + 1) / len(job.sources), f"Adding document {index + 1}")
        if not count:
            raise ConversionError("These PDFs contain no pages.")
        update(job, 90, "Writing merged PDF")
        with output.open("wb") as stream:
            writer.write(stream)
        return output
    finally:
        writer.close()


def _font():
    # Windows Arial or ReportLab's bundled Vera covers Latin and extended Latin.
    candidates = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/arial.ttf",
                  Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    import reportlab
    candidates.append(Path(reportlab.__file__).parent / "fonts/Vera.ttf")
    for path in candidates:
        if path.exists():
            if "FileForge" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("FileForge", str(path)))
            return "FileForge"
    return "Helvetica"


PDF_FONT = _font()


def cell_text(cell, cached, job):
    value = cell.value
    if cell.data_type == "f":
        value = cached.value
        if value is None:
            notice = "Some formulas have no saved result. Their formula text is shown. Open and save the workbook in Excel to include results."
            if notice not in job.warnings:
                job.warnings.append(notice)
            value = cell.value
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d %H:%M" if isinstance(value, datetime) and (value.hour or value.minute)
                              else "%Y-%m-%d")
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)) and "%" in cell.number_format:
        decimal_count = len(cell.number_format.split(".", 1)[1].split("%")[0]) if "." in cell.number_format else 0
        return f"{value:.{min(decimal_count, 6)}%}"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def spreadsheet_pdf(job):
    source = job.sources[0]
    update(job, 5, "Reading spreadsheet")
    sheets = []
    if source.suffix.lower() == ".csv":
        try:
            with source.open("r", encoding="utf-8-sig", newline="") as stream:
                sample = stream.read(8192)
                stream.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                except csv.Error:
                    dialect = csv.excel
                rows = []
                for row in csv.reader(stream, dialect):
                    checkpoint(job)
                    if len(rows) >= 10000 or len(row) > 80:
                        raise ConversionError("Table export supports up to 10,000 rows and 80 columns per sheet.")
                    rows.append(row)
                sheets.append((Path(job.filenames[0]).stem, rows))
        except UnicodeDecodeError as exc:
            raise ConversionError("Save the CSV with UTF-8 encoding and try again.") from exc
    else:
        with zipfile.ZipFile(source) as archive:
            if sum(entry.file_size for entry in archive.infolist()) > 200_000_000:
                raise ConversionError("This workbook is too large when expanded.")
        workbook = load_workbook(source, read_only=True, data_only=False, keep_links=False)
        cached = load_workbook(source, read_only=True, data_only=True, keep_links=False)
        try:
            for sheet in workbook:
                checkpoint(job)
                if sheet.sheet_state != "visible":
                    continue
                if sheet.max_row > 10000 or sheet.max_column > 80:
                    raise ConversionError("Table export supports up to 10,000 rows and 80 columns per sheet. Remove unused formatted rows if needed.")
                rows = []
                for cells, values in zip(sheet.iter_rows(), cached[sheet.title].iter_rows()):
                    checkpoint(job)
                    rows.append([cell_text(cell, value, job) for cell, value in zip(cells, values)])
                sheets.append((sheet.title, rows))
        finally:
            workbook.close()
            cached.close()
    checkpoint(job)
    page_size = landscape(A4) if job.options["orientation"] == "landscape" else A4
    doc = SimpleDocTemplate(str(job.directory / f"{Path(job.filenames[0]).stem}.pdf"), pagesize=page_size,
                            rightMargin=32, leftMargin=32, topMargin=34, bottomMargin=34,
                            title=Path(job.filenames[0]).stem, author="FileForge")
    style = ParagraphStyle("Cell", fontName=PDF_FONT, fontSize=8, leading=11,
                           textColor=colors.HexColor("#29313d"), splitLongWords=True)
    heading = ParagraphStyle("Heading", fontName=PDF_FONT, fontSize=16, leading=21,
                             textColor=colors.HexColor("#1c2838"), spaceAfter=16)
    story = []
    for title, rows in sheets:
        checkpoint(job)
        # Trim empty borders without dropping empty cells inside the data region.
        nonempty = [i for i, row in enumerate(rows) if any(value != "" for value in row)]
        if not nonempty:
            continue
        rows = rows[nonempty[0]:nonempty[-1] + 1]
        occupied = [i for row in rows for i, value in enumerate(row) if value != ""]
        first_col, last_col = min(occupied), max(occupied) + 1
        group_width = 8 if job.options["orientation"] == "landscape" else 5
        for first in range(first_col, last_col, group_width):
            checkpoint(job)
            if story:
                story.append(PageBreak())
            last = min(first + group_width, last_col)
            subtitle = f"{title} (columns {first + 1}-{last})" if last_col - first_col > group_width else title
            story.extend([Paragraph(escape(subtitle), heading), Spacer(1, 4)])
            data = []
            for row in rows:
                data.append([Paragraph(escape(str(row[col]) if col < len(row) else "").replace("\n", "<br/>"), style)
                             for col in range(first, last)])
            table = LongTable(data, colWidths=[(page_size[0] - 64) / (last - first)] * (last - first),
                              repeatRows=1, splitInRow=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe7ed")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f8")]),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d5dce2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(table)
    if not story:
        raise ConversionError("This spreadsheet has no visible data to export.")

    def footer(canvas, document):
        checkpoint(job)
        canvas.setFont(PDF_FONT, 8)
        canvas.setFillColor(colors.HexColor("#7a8491"))
        canvas.drawRightString(page_size[0] - 32, 18, f"Page {document.page}")

    update(job, 50, "Laying out PDF pages")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    job.warnings.append("Table export includes visible cell data. Charts, images, merged cells and Excel print layout are not retained.")
    return Path(doc.filename)


CONVERTERS = {
    "video": compress_video,
    "spreadsheet": spreadsheet_pdf,
    "image": convert_image,
    "merge": merge_pdf,
}
