import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.workspace import WORKSPACE, workspace_manifest
from tools.prepare_workspace import verify


@pytest.mark.skipif(not workspace_manifest(), reason='Run tools/prepare_workspace.py to include the offline workspace checks.')
def test_complete_workspace_is_pinned_and_does_not_contain_personal_site():
    manifest = verify()
    assert manifest['version'] == '0.3.0'
    assert manifest['task_count'] == 22 and manifest['tool_pages'] == 21
    paths = [item['path'] for item in manifest['files']]
    for required in ['tools/workspace/index.html', 'tools/word-to-pdf/index.html', 'tools/powerpoint-to-pdf/index.html', 'tools/csv-json/index.html', 'vendor/ffmpeg/ffmpeg-core.wasm', 'vendor/heic/heic-to.js', 'vendor/tesseract/lang/eng.traineddata.gz', 'THIRD_PARTY_NOTICES.md', 'SOURCE.md']:
        assert required in paths
    assert not any('skate-scape' in path or 'screenshots/' in path for path in paths)
    assert not (WORKSPACE / 'sw.js').exists()
    assert not (WORKSPACE / 'index.html').exists()
    assert list((WORKSPACE / 'licenses').glob('*.txt'))
    assert list((WORKSPACE / 'assets/models').glob('*.onnx'))
    html = (WORKSPACE / 'tools/workspace/index.html').read_text(encoding='utf-8')
    assert 'Native tools' in html and 'Desktop 0.3.0' in html
    assert 'data-open-offline' not in html and 'data-offline-panel' not in html
    assert 'Skate Scape' not in html and 'umut alisoglu' not in html


def test_native_routes_remain_local_and_health_distinguishes_modes():
    client = TestClient(app, base_url='http://127.0.0.1')
    response = client.get('/native/')
    assert response.status_code == 200 and 'Native conversion tools' in response.text
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    health = client.get('/api/health').json()
    assert health['version'] == '0.3.0' and len(health['tools']) == 9
    assert client.post('/api/jobs', headers={'origin': 'https://external.invalid'}).status_code == 403
    assert client.get('/', headers={'host': 'external.invalid'}).status_code == 400
    help_page = client.get('/desktop-help/')
    assert help_page.status_code == 200 and 'temporary job folders' in help_page.text
    client.close()


@pytest.mark.skipif(not workspace_manifest(), reason='Prepare the pinned workspace first.')
def test_workspace_serves_local_workers_and_allows_only_local_runtime_connections():
    client = TestClient(app, base_url='http://127.0.0.1')
    response = client.get('/')
    assert response.status_code == 200 and response.url.path == '/tools/workspace/'
    assert response.headers['cross-origin-opener-policy'] == 'same-origin'
    assert response.headers['cross-origin-embedder-policy'] == 'require-corp'
    csp = response.headers['content-security-policy']
    assert "worker-src 'self' blob:" in csp
    assert "connect-src 'self' blob:" in csp and 'https:' not in csp
    assert "frame-ancestors 'self'" in csp and "'wasm-unsafe-eval'" in csp
    assert "'unsafe-eval'" not in csp
    finish_worker = next((WORKSPACE / 'tools/_assets').glob('finish.worker-*.js'))
    worker_response = client.get('/tools/_assets/' + finish_worker.name)
    assert "'unsafe-eval'" in worker_response.headers['content-security-policy']
    for path in ['/tools/office-engine/', '/tools/', '/vendor/ffmpeg/ffmpeg-core.js', '/workspace-notices', '/workspace-source']:
        assert client.get(path).status_code == 200, path
    client.close()
