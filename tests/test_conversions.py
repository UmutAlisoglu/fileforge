"""End-to-end conversion checks using disposable fixtures, never user files."""
import io
import json
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader, PdfWriter

from app.main import app
from app.converters import media_info


@pytest.fixture(scope="module")
def client():
    with TestClient(app, base_url="http://127.0.0.1") as connected:
        yield connected


def submit(client, tool, files, options=None):
    response = client.post("/api/jobs", data={"tool": tool, "options": json.dumps(options or {})},
                           files=[("files", (name, content)) for name, content in files])
    assert response.status_code == 202, response.text
    return response.json()


def wait(client, identifier, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{identifier}").json()
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    pytest.fail("Conversion did not finish in time")


def download(client, job):
    assert job["status"] == "completed", job
    response = client.get(job["download_url"])
    assert response.status_code == 200
    return response.content


def image_bytes():
    result = io.BytesIO()
    Image.new("RGBA", (200, 100), (200, 20, 80, 0)).save(result, "PNG")
    return result.getvalue()


def pdf_bytes(width):
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=300)
    result = io.BytesIO()
    writer.write(result)
    return result.getvalue()


def workbook_bytes():
    # Minimal OOXML fixture with cached and uncached formulas plus a hidden sheet.
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        archive.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sales" sheetId="1" r:id="rId1"/><sheet name="Hidden" sheetId="2" state="hidden" r:id="rId2"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>')
        archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:C3"/><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>City</t></is></c><c r="B1" t="inlineStr"><is><t>Total</t></is></c><c r="C1" t="inlineStr"><is><t>Formula</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>München</t></is></c><c r="B2"><f>SUM(20,22)</f><v>42</v></c><c r="C2"><f>SUM(B2,8)</f><v/></c></row><row r="3"><c r="A3" t="inlineStr"><is><t>Berlin</t></is></c><c r="B3"><v>31</v></c></row></sheetData></worksheet>')
        archive.writestr("xl/worksheets/sheet2.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1"/><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Private hidden data</t></is></c></row></sheetData></worksheet>')
    return result.getvalue()


def test_image_resize_transparency_and_download(client):
    job = wait(client, submit(client, "image", [("picture.png", image_bytes())],
                             {"format": "jpg", "width": 100, "quality": 90})["id"])
    converted = Image.open(io.BytesIO(download(client, job)))
    assert converted.size == (100, 50)
    assert converted.mode == "RGB"
    assert all(value >= 250 for value in converted.getpixel((0, 0)))
    assert job["output_name"] == "picture-converted.jpg"
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 200
    assert client.get(job["download_url"]).status_code == 404


def test_image_pdf_is_readable(client):
    job = wait(client, submit(client, "image", [("picture.png", image_bytes())], {"format": "pdf"})["id"])
    assert len(PdfReader(io.BytesIO(download(client, job))).pages) == 1


def test_xlsx_cached_formula_unicode_and_hidden_sheet(client):
    job = wait(client, submit(client, "spreadsheet", [("sales.xlsx", workbook_bytes())])["id"])
    content = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(download(client, job))).pages)
    assert "München" in content
    assert "42" in content
    assert "=SUM(B2,8)" in content
    assert "Private hidden data" not in content
    assert any("no saved result" in warning for warning in job["warnings"])


def test_wide_csv_pagination_does_not_drop_rows_or_columns(client):
    rows = [",".join(f"Column{i}" for i in range(12))]
    rows += [",".join(f"R{row}C{col}" for col in range(12)) for row in range(130)]
    job = wait(client, submit(client, "spreadsheet", [("wide.csv", "\n".join(rows).encode())],
                             {"orientation": "portrait"})["id"])
    pages = PdfReader(io.BytesIO(download(client, job))).pages
    text = "\n".join(page.extract_text() for page in pages)
    assert len(pages) >= 6
    assert "R129C11" in text
    assert "R0C0" in text
    assert "Column11" in text


def test_pdf_merge_preserves_input_order(client):
    job = wait(client, submit(client, "merge", [("second.pdf", pdf_bytes(220)), ("first.pdf", pdf_bytes(110))])["id"])
    pages = PdfReader(io.BytesIO(download(client, job))).pages
    assert [float(page.mediabox.width) for page in pages] == [220, 110]


def test_encrypted_pdf_fails_clearly(client):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret")
    encrypted = io.BytesIO()
    writer.write(encrypted)
    job = wait(client, submit(client, "merge", [("locked.pdf", encrypted.getvalue()), ("open.pdf", pdf_bytes(110))])["id"])
    assert job["status"] == "failed"
    assert "password protected" in job["error"]


def test_validation_corrupt_file_and_foreign_origin(client):
    assert client.post("/api/jobs", data={"tool": "video", "options": '{"target_mb": "NaN"}'},
                       files={"files": ("v.mp4", b"fake")}).status_code == 400
    assert client.post("/api/jobs", data={"tool": "image"},
                       files={"files": ("bad.exe", b"fake")}).status_code == 400
    assert client.post("/api/jobs", headers={"Origin": "https://example.com"},
                       data={"tool": "image"}, files={"files": ("i.png", image_bytes())}).status_code == 403
    corrupt = wait(client, submit(client, "image", [("broken.png", b"not an image")])["id"])
    assert corrupt["status"] == "failed"
    assert corrupt["download_url"] is None


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg unavailable")
def test_real_video_target_size_duration_and_audio(client, tmp_path):
    video = tmp_path / "source.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc2=size=320x240:rate=20", "-f", "lavfi", "-i", "sine=frequency=440",
                    "-t", "6", "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-y", str(video)],
                   check=True, timeout=30, capture_output=True)
    job = wait(client, submit(client, "video", [("source.mp4", video.read_bytes())],
                             {"target_mb": 0.15, "height": 480})["id"])
    result = tmp_path / "compressed.mp4"
    result.write_bytes(download(client, job))
    info = media_info(result)
    assert result.stat().st_size <= 150000
    assert float(info["format"]["duration"]) >= 5.8
    assert any(stream["codec_type"] == "audio" for stream in info["streams"])
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(result),
                    "-f", "null", "-"], check=True, timeout=30, capture_output=True)
    silent = wait(client, submit(client, "video", [("source.mp4", video.read_bytes())],
                                {"target_mb": 0.1, "remove_audio": True, "height": 480})["id"])
    silent_path = tmp_path / "silent.mp4"
    silent_path.write_bytes(download(client, silent))
    assert not any(stream["codec_type"] == "audio" for stream in media_info(silent_path)["streams"])


def test_cancel_queued_or_running_job(client, monkeypatch):
    from app.main import CONVERTERS
    from app.converters import checkpoint

    def slow(job):
        for _ in range(200):
            checkpoint(job)
            job.cancel.wait(0.05)
        raise AssertionError("Cancellation was not received")

    monkeypatch.setitem(CONVERTERS, "image", slow)
    identifier = submit(client, "image", [("image.png", image_bytes())])["id"]
    assert client.post(f"/api/jobs/{identifier}/cancel").status_code == 200
    job = wait(client, identifier)
    assert job["status"] == "cancelled"
    assert job["download_url"] is None


def test_toolbox_health_validation_and_private_preview(client):
    health = client.get('/api/health').json()
    assert health['version'] == '0.3.0'
    assert len(health['tools']) == 9 and 'pdfpreview' not in health['tools']
    bad = [('background', {'fill': 'remote'}), ('trace', {'precision': True}),
           ('crop', {'x': 0, 'y': 0, 'width': -1, 'height': 20}),
           ('pdfimages', {'edge': 9999}), ('organize', {'pages': []})]
    for tool, options in bad:
        response = client.post('/api/jobs', data={'tool': tool, 'options': json.dumps(options)},
                               files={'files': ('source.pdf' if tool in {'organize', 'pdfimages'} else 'source.png', b'fixture')})
        assert response.status_code == 400
    job = wait(client, submit(client, 'image', [('source.png', image_bytes())], {'format': 'png'})['id'])
    preview = client.get(job['preview_url'])
    assert preview.status_code == 200 and preview.headers['content-type'].startswith('image/png')
    assert preview.headers['cache-control'] == 'no-store'
    assert Image.open(io.BytesIO(preview.content)).size == (200, 100)
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 200
    assert client.get(job['preview_url']).status_code == 404


def test_batch_images_keep_duplicate_names_distinct_and_combine_pdf(client):
    files = [('Photo.png', image_bytes()), ('photo.PNG', image_bytes())]
    job = wait(client, submit(client, 'image', files, {'format': 'png', 'width': 100})['id'])
    with zipfile.ZipFile(io.BytesIO(download(client, job))) as archive:
        names = archive.namelist()
        assert len(names) == len({name.lower() for name in names}) == 2
        for name in names:
            assert Image.open(io.BytesIO(archive.read(name))).size == (100, 50)
    combined = wait(client, submit(client, 'image', files, {'format': 'pdf'})['id'])
    assert len(PdfReader(io.BytesIO(download(client, combined))).pages) == 2


def test_pdf_preview_and_organizer_use_source_pages_and_rotation(client):
    files = [('first.pdf', pdf_bytes(100)), ('second.pdf', pdf_bytes(200))]
    preview = wait(client, submit(client, 'pdfpreview', files)['id'])
    cards = json.loads(download(client, preview))['pages']
    assert len(cards) == 2
    assert cards[1]['file_index'] == 1 and cards[1]['page_index'] == 0
    assert cards[0]['thumbnail'].startswith('data:image/png;base64,')
    plan = [{'file_index': 1, 'page_index': 0, 'rotation': 90}, {'file_index': 0, 'page_index': 0, 'rotation': 0}]
    job = wait(client, submit(client, 'organize', files, {'pages': plan})['id'])
    pages = PdfReader(io.BytesIO(download(client, job))).pages
    assert len(pages) == 2
    assert float(pages[0].mediabox.width) == 200 and pages[0].rotation == 90
    assert float(pages[1].mediabox.width) == 100
