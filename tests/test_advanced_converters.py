"""Real pixel, vector, and PDF exports from disposable local fixtures."""
import base64
import io
import json
import multiprocessing.process
import threading
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from app import advanced_converters as engines
from app.converters import Cancelled, ConversionError


def job_for(tmp_path, files, options=None):
    directory = tmp_path / "job"
    directory.mkdir()
    sources = []
    for index, (name, content) in enumerate(files):
        path = directory / f"source-{index}{Path(name).suffix}"
        path.write_bytes(content)
        sources.append(path)
    return SimpleNamespace(directory=directory, sources=sources,
                           filenames=[name for name, _ in files], options=options or {},
                           cancel=threading.Event(), warnings=[], progress=0, stage="Starting")


def image_bytes(image, format="PNG", **settings):
    buffer = io.BytesIO()
    image.save(buffer, format, **settings)
    return buffer.getvalue()


def pdf_bytes():
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=(300, 200))
    for number, (width, height, colour) in enumerate([(300, 200, (1, 0, 0)),
                                                     (200, 300, (0, 1, 0)),
                                                     (200, 300, (0, 0, 1))], 1):
        document.setPageSize((width, height))
        document.setFillColorRGB(*colour)
        document.rect(0, 0, width, height, fill=1, stroke=0)
        document.setFillColorRGB(1, 1, 1)
        document.drawString(30, 70, f"Source page {number}")
        document.showPage()
    document.save()
    reader = PdfReader(io.BytesIO(buffer.getvalue()))
    writer = PdfWriter()
    for number, page in enumerate(reader.pages):
        writer.add_page(page)
        if number == 1:
            writer.pages[-1].rotate(90)
    result = io.BytesIO()
    writer.write(result)
    writer.close()
    return result.getvalue()


def test_crop_exports_exact_selected_pixels_and_no_metadata(tmp_path):
    image = Image.new("RGBA", (240, 160), "red")
    draw = ImageDraw.Draw(image)
    draw.rectangle((120, 80, 239, 159), fill=(18, 79, 195, 255))
    job = job_for(tmp_path, [("quadrants.png", image_bytes(image))],
                  {"x": 120, "y": 80, "width": 100, "height": 60, "format": "png"})
    with Image.open(engines.crop_image(job)) as output:
        assert output.size == (100, 60)
        assert output.getextrema() == ((18, 18), (79, 79), (195, 195), (255, 255))
        assert not output.getexif()


def test_crop_uses_exif_upright_coordinates_and_rejects_outside(tmp_path):
    image = Image.new("RGB", (60, 20), "red")
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "Private source description"
    job = job_for(tmp_path, [("rotated.jpg", image_bytes(image, "JPEG", exif=exif))],
                  {"x": 0, "y": 20, "width": 20, "height": 30, "format": "jpg"})
    with Image.open(engines.crop_image(job)) as output:
        assert output.size == (20, 30)
        assert not output.getexif()
    job.options["x"] = 30
    with pytest.raises(ConversionError, match="upright image"):
        engines.crop_image(job)


def test_crop_jpg_flattens_transparency_on_white(tmp_path):
    job = job_for(tmp_path, [("alpha.png", image_bytes(Image.new("RGBA", (20, 20), (90, 30, 20, 0))))],
                  {"x": 0, "y": 0, "width": 20, "height": 20, "format": "jpg"})
    with Image.open(engines.crop_image(job)) as output:
        assert output.mode == "RGB"
        assert output.getpixel((0, 0)) == (255, 255, 255)


@pytest.mark.parametrize("value,expected", [("all", [0, 1, 2]), ("", [0, 1, 2]),
                                            ("3, 1, 3", [2, 0]), (" 1 - 2 ,3", [0, 1, 2])])
def test_page_selection_range_order_and_duplicates(value, expected):
    assert engines.parse_pages(value, 3) == expected


@pytest.mark.parametrize("value", ["0", "4", "2-1", "1-4", "1,", "nan", "1.5", "-1", "1--2"])
def test_page_selection_rejects_invalid_ranges(value):
    with pytest.raises(ConversionError):
        engines.parse_pages(value, 3)


def test_page_export_limit_is_applied_before_rendering():
    with pytest.raises(ConversionError, match="100"):
        engines.parse_pages("all", 101)
    with pytest.raises(ConversionError, match="100"):
        engines.parse_pages("1-101", 5000)


def test_pdf_images_zip_contains_real_content_in_selected_order(tmp_path):
    job = job_for(tmp_path, [("colours.pdf", pdf_bytes())],
                  {"pages": "3,1,3", "edge": 1200, "format": "png"})
    with zipfile.ZipFile(engines.pdf_images(job)) as archive:
        assert archive.namelist() == ["colours-page-0003.png", "colours-page-0001.png"]
        with Image.open(io.BytesIO(archive.read(archive.namelist()[0]))) as blue:
            assert blue.size == (800, 1200)
            assert blue.convert("RGB").getpixel((10, 10)) == (0, 0, 255)
        with Image.open(io.BytesIO(archive.read(archive.namelist()[1]))) as red:
            assert red.size == (1200, 800)
            assert red.convert("RGB").getpixel((10, 10)) == (255, 0, 0)


def test_pdf_images_single_jpg_respects_existing_page_rotation(tmp_path):
    job = job_for(tmp_path, [("colours.pdf", pdf_bytes())],
                  {"pages": "2", "edge": 1200, "format": "jpg"})
    output = engines.pdf_images(job)
    assert output.suffix == ".jpg"
    with Image.open(output) as image:
        assert image.size == (1200, 800)
        assert all(abs(actual - expected) < 4 for actual, expected in zip(image.getpixel((10, 10)), (0, 255, 0)))


def test_pdf_preview_has_real_thumbnails_and_source_indices(tmp_path):
    job = job_for(tmp_path, [("one.pdf", pdf_bytes()), ("two.pdf", pdf_bytes())])
    result = json.loads(engines.pdf_preview(job).read_text(encoding="utf-8"))
    assert result["file_count"] == 2
    assert len(result["pages"]) == 6
    assert [(page["file_index"], page["page_index"]) for page in result["pages"]] == [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)]
    rotated = result["pages"][1]
    assert (rotated["width"], rotated["height"]) == (300, 200)
    assert rotated["rotation"] == 0 and rotated["selected"] is True
    assert rotated["name"] == "one.pdf"
    with Image.open(io.BytesIO(base64.b64decode(rotated["thumbnail"].split(",")[1]))) as thumbnail:
        assert thumbnail.size == (240, 160)
        assert thumbnail.convert("RGB").getpixel((5, 5)) == (0, 255, 0)


def test_pdf_organizer_preserves_text_order_and_independent_rotations(tmp_path):
    job = job_for(tmp_path, [("one.pdf", pdf_bytes()), ("two.pdf", pdf_bytes())],
                  {"pages": [{"file_index": 1, "page_index": 2, "rotation": 90},
                             {"file_index": 0, "page_index": 0, "rotation": 180},
                             {"file_index": 0, "page_index": 0, "rotation": 0},
                             {"file_index": 0, "page_index": 1, "rotation": 270}]})
    result = PdfReader(engines.organize_pdf(job))
    assert [page.extract_text().strip() for page in result.pages] == ["Source page 3", "Source page 1", "Source page 1", "Source page 2"]
    assert [page.rotation % 360 for page in result.pages] == [90, 180, 0, 0]
    assert len(PdfReader(job.sources[0]).pages) == 3
    assert PdfReader(job.sources[0]).pages[0].rotation == 0


def test_pdf_organizer_rejects_missing_source_page(tmp_path):
    job = job_for(tmp_path, [("one.pdf", pdf_bytes())],
                  {"pages": [{"file_index": 0, "page_index": 3, "rotation": 0}]})
    with pytest.raises(ConversionError, match="invalid"):
        engines.organize_pdf(job)


@pytest.mark.parametrize("engine", [engines.pdf_preview, engines.pdf_images, engines.organize_pdf])
def test_locked_pdf_is_rejected_without_password_attempts(tmp_path, engine):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret")
    buffer = io.BytesIO()
    writer.write(buffer)
    writer.close()
    job = job_for(tmp_path, [("private.pdf", buffer.getvalue())])
    with pytest.raises(ConversionError, match="password protected"):
        engine(job)


def test_pdf_preview_page_limit_is_applied_before_rendering(tmp_path):
    writer = PdfWriter()
    for _ in range(201):
        writer.add_blank_page(width=20, height=20)
    buffer = io.BytesIO()
    writer.write(buffer)
    writer.close()
    job = job_for(tmp_path, [("many.pdf", buffer.getvalue())])
    with pytest.raises(ConversionError, match="200 pages"):
        engines.pdf_preview(job)


def test_pdf_output_byte_limit_and_cancellation(tmp_path, monkeypatch):
    job = job_for(tmp_path, [("colour.pdf", pdf_bytes())], {"pages": "all", "edge": 1200})
    monkeypatch.setattr(engines, "MAX_PDF_OUTPUT", 1)
    with pytest.raises(ConversionError, match="500 MB"):
        engines.pdf_images(job)
    job.cancel.set()
    with pytest.raises(Cancelled):
        engines.pdf_images(job)


def test_trace_produces_vector_paths_and_preserves_transparent_canvas(tmp_path):
    image = Image.new("RGBA", (160, 100), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 70, 80), fill=(255, 0, 0, 255))
    draw.ellipse((80, 20, 140, 80), fill=(0, 0, 255, 255))
    job = job_for(tmp_path, [("logo.png", image_bytes(image))], {"precision": 6, "detail": "fine"})
    result = engines.trace_image(job)
    root = ElementTree.fromstring(result.read_text(encoding="utf-8"))
    assert root.tag.endswith("svg")
    assert root.attrib["width"] == "160" and root.attrib["height"] == "100"
    paths = [node for node in root.iter() if node.tag.endswith("path")]
    assert len(paths) >= 2
    assert all(node.attrib.get("d") for node in paths)
    assert not any(node.tag.endswith("image") for node in root.iter())
    assert not any(node.tag.endswith("script") for node in root.iter())
    assert not (job.directory / "trace-input.png").exists()
    text = result.read_text(encoding="utf-8").lower()
    assert "#ff0000" in text and "#0000ff" in text
    # Fully transparent source canvas is not traced as an opaque black box.
    assert "#000000" not in text


def test_trace_scales_large_canvas_and_cancellation(tmp_path):
    image = Image.new("RGB", (2100, 300), "red")
    job = job_for(tmp_path, [("wide.png", image_bytes(image))], {"precision": 4, "detail": "simple"})
    root = ElementTree.fromstring(engines.trace_image(job).read_text(encoding="utf-8"))
    assert root.attrib["width"] == "2000"
    assert any("scaled" in notice for notice in job.warnings)
    job.cancel.set()
    with pytest.raises(Cancelled):
        engines.trace_image(job)


def test_trace_running_native_worker_is_stopped_on_cancel(tmp_path, monkeypatch):
    job = job_for(tmp_path, [("logo.png", image_bytes(Image.new("RGBA", (800, 800), "red")))],
                  {"precision": 6, "detail": "fine"})
    original_start = multiprocessing.process.BaseProcess.start
    spawned, timers = [], []

    def start_and_cancel(process):
        original_start(process)
        spawned.append(process)
        timer = threading.Timer(0.05, job.cancel.set)
        timers.append(timer)
        timer.start()

    monkeypatch.setattr(multiprocessing.process.BaseProcess, "start", start_and_cancel)
    began = time.monotonic()
    with pytest.raises(Cancelled):
        engines.trace_image(job)
    for timer in timers:
        timer.join(timeout=1)
    assert len(spawned) == 1 and spawned[0]._closed
    assert time.monotonic() - began < 3
    assert not (job.directory / "trace-input.png").exists()


HORSE = Path(__file__).resolve().parents[1] / ".qa" / "fixtures" / "u2net-horse.jpg"


@pytest.mark.skipif(not HORSE.is_file() or not engines.MODEL.is_file(), reason="Bundled model or local QA image unavailable")
def test_real_background_model_retains_subject_and_original_transparency(tmp_path):
    job = job_for(tmp_path, [("horse.jpg", HORSE.read_bytes())], {"fill": "transparent"})
    with Image.open(engines.remove_background(job)) as image:
        assert image.size == (770, 595)
        alpha = image.getchannel("A")
        histogram = alpha.histogram()
        assert sum(histogram[:16]) / (image.width * image.height) > 0.25
        assert sum(histogram[240:]) / (image.width * image.height) > 0.15
        assert alpha.getpixel((385, 297)) > 220
        assert alpha.getpixel((77, 29)) < 30
        assert not image.getexif()
    with Image.open(io.BytesIO(HORSE.read_bytes())) as source:
        transparent = source.convert("RGBA")
    ImageDraw.Draw(transparent).rectangle((375, 287, 395, 307), fill=(255, 255, 255, 0))
    job.sources[0].write_bytes(image_bytes(transparent))
    transparent.close()
    with Image.open(engines.remove_background(job)) as image:
        assert image.getpixel((385, 297))[3] == 0


@pytest.mark.skipif(not HORSE.is_file() or not engines.MODEL.is_file(), reason="Bundled model or local QA image unavailable")
def test_background_white_result_and_active_inference_cancellation(tmp_path, monkeypatch):
    job = job_for(tmp_path, [("horse.jpg", HORSE.read_bytes())], {"fill": "white"})
    with Image.open(engines.remove_background(job)) as image:
        assert image.getchannel("A").getextrema() == (255, 255)
        assert all(value > 247 for value in image.getpixel((77, 29))[:3])
    original_update = engines.update

    def cancel_when_running(current, progress, stage):
        original_update(current, progress, stage)
        if stage == "Finding the subject on your device":
            current.cancel.set()

    monkeypatch.setattr(engines, "update", cancel_when_running)
    with pytest.raises(Cancelled):
        engines.remove_background(job)
