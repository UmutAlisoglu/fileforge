"""Exercise actual native conversion dependencies through the local job service."""
from __future__ import annotations

import io
import json
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path


def _request(url, method="GET", data=None, headers=None):
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read()


def _multipart(tool, options, filename, content):
    boundary = "FileForgeSmoke" + uuid.uuid4().hex
    parts = []
    for name, value in (("tool", tool), ("options", json.dumps(options))):
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode())
    parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode())
    parts.append(content)
    parts.append((f"\r\n--{boundary}--\r\n").encode())
    return b"".join(parts), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def _convert(url, tool, options, filename, content, check):
    """Keep every test job disposable, including a failed or timed-out job."""
    identifier = None
    try:
        body, headers = _multipart(tool, options, filename, content)
        job = json.loads(_request(url + "/api/jobs", "POST", body, headers))
        identifier = job["id"]
        deadline = time.monotonic() + 60
        while job["status"] not in {"completed", "failed", "cancelled"}:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"The frozen {tool} conversion exceeded 60 seconds.")
            time.sleep(0.2)
            job = json.loads(_request(url + "/api/jobs/" + identifier))
        if job["status"] != "completed":
            raise RuntimeError(job.get("error") or f"The {tool} conversion ended as {job['status']}.")
        result = _request(url + job["download_url"])
        return {"ok": True, "output": job["output_name"], "bytes": len(result), **check(result)}
    except Exception as error:
        return {"ok": False, "error": str(error)}
    finally:
        if identifier:
            try:
                _request(url + f"/api/jobs/{identifier}/cancel", "POST", b"")
                cleanup_deadline = time.monotonic() + 10
                while time.monotonic() < cleanup_deadline:
                    current = json.loads(_request(url + "/api/jobs/" + identifier))
                    if current["status"] in {"completed", "failed", "cancelled"}:
                        _request(url + "/api/jobs/" + identifier, "DELETE")
                        break
                    time.sleep(0.2)
            except Exception:
                # Closing the app also cancels jobs; the janitor owns expiry.
                pass


def run_checks(url, background_image=None):
    """No external request or private fixture is needed for these checks."""
    from PIL import Image, ImageDraw, ImageOps
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas

    results = {}
    picture = Image.new("RGBA", (128, 96), (30, 60, 210, 255))
    draw = ImageDraw.Draw(picture)
    draw.rectangle((0, 0, 63, 47), fill=(230, 40, 50, 255))
    draw.rectangle((96, 64, 127, 95), fill=(0, 0, 0, 0))
    source = io.BytesIO()
    picture.save(source, format="PNG")

    def check_crop(content):
        with Image.open(io.BytesIO(content)) as result:
            result.load()
            if result.format != "PNG" or result.mode != "RGBA" or result.size != (32, 24):
                raise AssertionError("The native crop did not produce the expected RGBA PNG dimensions.")
            if result.getpixel((0, 0)) != (230, 40, 50, 255):
                raise AssertionError("The cropped pixels do not match the source selection.")
            return {"dimensions": list(result.size), "mode": result.mode}

    results["crop"] = _convert(url, "crop", {"x": 4, "y": 4, "width": 32, "height": 24, "format": "png"}, "native-smoke.png", source.getvalue(), check_crop)

    def check_trace(content):
        svg = ET.fromstring(content)
        paths = [node for node in svg.iter() if node.tag.rsplit("}", 1)[-1] == "path" and node.get("d")]
        images = [node for node in svg.iter() if node.tag.rsplit("}", 1)[-1] == "image"]
        if svg.tag.rsplit("}", 1)[-1] != "svg" or not paths or images or b"data:image" in content:
            raise AssertionError("The frozen SVG engine did not create standalone vector paths.")
        return {"paths": len(paths), "embedded_images": len(images)}

    results["trace"] = _convert(url, "trace", {"precision": 4, "detail": "balanced"}, "native-smoke.png", source.getvalue(), check_trace)

    generated_pdf = io.BytesIO()
    document = canvas.Canvas(generated_pdf, pagesize=(144, 72))
    document.setFillColorRGB(1, 0, 0)
    document.rect(0, 0, 144, 72, fill=1, stroke=0)
    document.save()
    writer = PdfWriter()
    writer.add_page(PdfReader(io.BytesIO(generated_pdf.getvalue())).pages[0])
    pdf = io.BytesIO()
    writer.write(pdf)

    def check_pdf_image(content):
        with Image.open(io.BytesIO(content)) as result:
            result.load()
            if result.format != "PNG" or result.size != (1200, 600):
                raise AssertionError("PDFium did not render the expected PNG page dimensions.")
            red, green, blue = result.convert("RGB").getpixel((600, 300))
            if red < 240 or green > 20 or blue > 20:
                raise AssertionError("The rendered PDF pixels do not match the test page.")
            return {"dimensions": list(result.size), "mode": result.mode}

    results["pdfimages"] = _convert(url, "pdfimages", {"pages": "1", "edge": 1200, "format": "png"}, "native-smoke.pdf", pdf.getvalue(), check_pdf_image)

    if background_image:
        try:
            image_path = Path(background_image)
            with Image.open(image_path) as original:
                expected_size = ImageOps.exif_transpose(original).size

            def check_background(content):
                with Image.open(io.BytesIO(content)) as result:
                    result.load()
                    if result.format != "PNG" or result.mode != "RGBA" or result.size != expected_size:
                        raise AssertionError("The bundled background engine did not preserve PNG dimensions and alpha.")
                    alpha = result.getchannel("A")
                    histogram = alpha.histogram()
                    removed = sum(histogram[:32])
                    retained = sum(histogram[241:])
                    if removed < 100 or retained < 100:
                        raise AssertionError("The actual model did not both remove a background and retain a subject.")
                    return {"dimensions": list(result.size), "alpha_extrema": list(alpha.getextrema()), "removed_pixels": removed, "retained_pixels": retained}

            results["background"] = _convert(url, "background", {"fill": "transparent"}, "native-subject" + image_path.suffix.lower(), image_path.read_bytes(), check_background)
        except Exception as error:
            results["background"] = {"ok": False, "error": str(error)}
    return results
