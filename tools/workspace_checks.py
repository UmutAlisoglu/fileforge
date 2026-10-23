"""Check real WebView2 worker/rendering outputs, not only packaged file presence."""
import base64
import io
import json
from pathlib import Path
import threading


def run_checks(window, heic_image=None):
    from pypdf import PdfReader
    root = Path(__file__).resolve().parents[1]
    fixtures = {extension: base64.b64encode((root / f'tests/fixtures/sample.{extension}').read_bytes()).decode('ascii') for extension in ('docx', 'pptx')}
    if heic_image:
        fixtures['heic'] = base64.b64encode(Path(heic_image).read_bytes()).decode('ascii')
    script = Path(__file__).with_suffix('.js').read_text(encoding='utf-8')
    completed = threading.Event()
    received = {}

    def callback(value):
        if isinstance(value, dict):
            received.update(value)
        else:
            received['script'] = {'ok': False, 'error': str(value)}
        completed.set()

    window.evaluate_js(f'({script})({json.dumps(fixtures)})', callback=callback)
    if not completed.wait(210):
        raise TimeoutError('The native WebView2 workspace checks exceeded 210 seconds.')
    for name, check in received.items():
        encoded = check.pop('base64', None)
        if not check.get('ok'):
            continue
        try:
            content = base64.b64decode(encoded, validate=True)
            if name.endswith('_pdf'):
                document = PdfReader(io.BytesIO(content))
                check['pages'] = len(document.pages)
                if name == 'text_pdf':
                    text = ''.join(page.extract_text() for page in document.pages)
                    if 'FileForge desktop release check.' not in text or 'Merhaba' not in text:
                        raise AssertionError('The workspace text PDF has no expected selectable text.')
                elif len(document.pages) != 2 or check.get('preview_pages') != 2 or not document.pages[0].images:
                    raise AssertionError('The Office fixture did not export two real page images.')
            elif name == 'heic_jpg':
                from PIL import Image
                with Image.open(io.BytesIO(content)) as image:
                    image.load()
                    if image.format != 'JPEG' or min(image.size) <= 0:
                        raise AssertionError('The packaged HEIC worker did not produce a real JPEG.')
                    check['dimensions'] = list(image.size)
            elif name == 'json_csv' and content.decode('utf-8-sig') != '"name","count"\r\n"Sample","2"':
                raise AssertionError('JSON to CSV produced incorrect data.')
        except Exception as error:
            check.update(ok=False, error=str(error))
    if not {'text_pdf', 'json_csv', 'docx_pdf', 'pptx_pdf'}.issubset(received):
        received['complete'] = {'ok': False, 'error': 'A workspace conversion check did not return.'}
    return received
