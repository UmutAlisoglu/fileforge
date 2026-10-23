"""Build a pinned FileForge workspace, including every offline engine, for Windows.

Generated files stay outside the executable so LGPL components remain replaceable.
No visitor documents, credentials, Git metadata or personal-site pages are copied.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PIN = json.loads((ROOT / 'workspace-source.json').read_text())
OUTPUT = ROOT / 'app/workspace'

HEADER = '''function header(path) {
  return `<a class="skip-link" href="#main">Skip to content</a><header class="site-header wrap hub-header"><a class="wordmark" href="/tools/workspace/"><span class="monogram">f.</span><span>FileForge<small>Desktop 0.3.0 · on your device</small></span></a><nav aria-label="Main navigation"><a href="/tools/workspace/"${path === '/tools/workspace/' ? ' aria-current="page"' : ''}>Workspace</a><a href="/tools/"${path !== '/tools/workspace/' ? ' aria-current="page"' : ''}>All tools</a><a href="/native/">Native tools</a><button type="button" data-open-tools class="tool-switcher-trigger" hidden>Find a tool</button><a href="/desktop-help/">Help</a></nav></header>`;
}
const footer = `<footer class="site-footer wrap new-footer"><a class="footer-brand" href="/tools/workspace/">FileForge<small>Desktop 0.3.0</small></a><div><a href="/tools/workspace/">Connected workspace</a><a href="/tools/">All tools</a><a href="/native/">Native tools for larger files</a><a href="/desktop-help/">Privacy &amp; help</a><a href="/workspace-notices">Component notices</a></div><p class="footer-note"><span>Processing stays on your computer. Download results before closing.</span><span>Engines included · no account</span></p></footer>`;

'''


def prepare_source(source):
    templates = source / 'src/site/templates.js'
    text = templates.read_text(encoding='utf-8')
    start, end = text.index('function header(path)'), text.index('// Vite expands')
    text = text[:start] + HEADER + text[end:]
    text = text.replace('<script type="module" src="/src/site/offline.js"></script>', '')
    text = text.replace('<link rel="manifest" href="/manifest.webmanifest">', '')
    templates.write_text(text, encoding='utf-8')
    workspace_js = source / 'src/site/workspace.js'
    workspace_js.write_text(workspace_js.read_text(encoding='utf-8').replace('Saved on this device. No files or filenames.', 'Kept for this session. No files or filenames.'), encoding='utf-8')
    workspace_template = source / 'src/site/workspace-template.html'
    workspace_template.write_text(workspace_template.read_text(encoding='utf-8').replace('Remember my favourite tools', 'Keep favourites for this session'), encoding='utf-8')
    usage = source / 'src/site/tool-usage.js'
    usage.write_text(usage.read_text(encoding='utf-8').replace('/projects/fileforge/#desktop', '/native/').replace('Bigger files? FileForge for Windows →', 'Larger files? Open native tools →'), encoding='utf-8')
    switcher = source / 'src/site/tool-switcher.js'
    switcher.write_text(switcher.read_text(encoding='utf-8').replace('href="/contact/"', 'href="mailto:umut@alisoglu.com"'), encoding='utf-8')
    for path in (source / 'tools').rglob('*.html'):
        text = path.read_text(encoding='utf-8')
        text = re.sub(r'<p class="forge-offline-link">.*?</p>', '', text)
        text = text.replace('<section data-offline-panel></section>', '')
        text = text.replace('This is FileForge for the browser. The Windows app has a different feature set.', 'This workspace runs inside FileForge Desktop. Native tools offer larger file limits.')
        text = text.replace('href="/projects/fileforge/#compare-title"', 'href="/desktop-help/"').replace('Compare the editions →', 'Compare the modes →')
        text = text.replace('href="/privacy/"', 'href="/desktop-help/"').replace('href="/contact/"', 'href="mailto:umut@alisoglu.com"')
        text = text.replace('href="/assets/monogram.svg"', 'href="/assets/fileforge.svg"')
        text = re.sub(r'(<title>.*?)(?:Alisoglu|Alisoğlu)(</title>)', r'\1FileForge Desktop\2', text)
        path.write_text(text, encoding='utf-8')


def included(relative):
    name = relative.as_posix()
    if relative.suffix == '.md' and name.startswith('tools/'):
        return False
    if name.startswith('assets/screenshots/') or re.search(r'(?:skate-scape|repodock|social-card).*\.(?:png|jpg|svg)$', name):
        return False
    return name.startswith(('tools/', 'vendor/', 'fonts/', 'licenses/', 'icons/', 'assets/')) or name == 'THIRD_PARTY_NOTICES.md'


def verify(directory=OUTPUT):
    manifest = json.loads((directory / 'workspace-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('project') != 'FileForge workspace' or manifest.get('source_commit') != PIN['commit']:
        raise RuntimeError('Workspace pin does not match workspace-source.json. Rebuild it before packaging.')
    root = directory.resolve()
    for entry in manifest['files']:
        file = (root / entry['path']).resolve()
        if not file.is_relative_to(root) or not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != entry['sha256']:
            raise RuntimeError(f"Workspace file is missing or changed: {entry['path']}")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, help='Use the pinned commit from a local website Git repository, including no uncommitted changes.')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        manifest = verify()
        print(f"Verified {len(manifest['files'])} pinned workspace files.")
        return
    work = ROOT / '.build'
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='workspace-', dir=work) as temporary:
        scratch = Path(temporary).resolve()
        source = scratch / 'source'
        source.mkdir()
        repository = args.source.resolve() if args.source else scratch / 'repository'
        if not args.source:
            subprocess.run(['git', 'clone', '--no-checkout', PIN['repository'], str(repository)], check=True)
        archive = scratch / 'source.tar'
        with archive.open('wb') as output:
            subprocess.run(['git', '-C', str(repository), 'archive', '--format=tar', PIN['commit']], stdout=output, check=True)
        with tarfile.open(archive) as bundle:
            bundle.extractall(source, filter='data')
        prepare_source(source)
        npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
        if not npm:
            raise RuntimeError('Node.js 24 and npm are needed to prepare the workspace, not to run the finished app.')
        subprocess.run([npm, 'ci', '--no-audit', '--no-fund'], cwd=source, check=True)
        subprocess.run([npm, 'run', 'build'], cwd=source, check=True)
        prepared = scratch / 'workspace'
        prepared.mkdir()
        for file in (source / 'dist').rglob('*'):
            if file.is_file() and included(file.relative_to(source / 'dist')):
                destination = prepared / file.relative_to(source / 'dist')
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(file, destination)
        # Preserve all component notices, source links, licenses and replaceable
        # worker modules. Personal-site/game imagery is not part of this bundle.
        notices = prepared / 'THIRD_PARTY_NOTICES.md'
        text = notices.read_text(encoding='utf-8')
        text = re.sub(r'The Skate Scape gameplay screenshots.*?\n\n', '', text)
        notices.write_text(text, encoding='utf-8')
        (prepared / 'SOURCE.md').write_text(f"# FileForge Desktop workspace source\n\nWebsite source: {PIN['repository']}\n\nExact commit: {PIN['commit']}\n\nDesktop build adaptations: https://github.com/UmutAlisoglu/fileforge/blob/v{PIN['version']}/tools/prepare_workspace.py\n\nAll engines, fonts and language data are local. LGPL worker modules in vendor/ are ordinary replaceable files. Component source links, build references and licenses are provided in THIRD_PARTY_NOTICES.md and licenses/.\n", encoding='utf-8')
        entries = [{'path': file.relative_to(prepared).as_posix(), 'bytes': file.stat().st_size, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()} for file in sorted(prepared.rglob('*')) if file.is_file()]
        manifest = {'project': 'FileForge workspace', 'version': PIN['version'], 'source_repository': PIN['repository'], 'source_commit': PIN['commit'], 'task_count': PIN['task_count'], 'tool_pages': PIN['tool_pages'], 'files': entries}
        (prepared / 'workspace-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        if OUTPUT.exists():
            existing = json.loads((OUTPUT / 'workspace-manifest.json').read_text(encoding='utf-8'))
            expected_output = (ROOT / 'app').resolve() / 'workspace'
            if OUTPUT.resolve() != expected_output or OUTPUT.is_symlink() or OUTPUT.is_junction() or existing.get('project') != 'FileForge workspace':
                raise RuntimeError('Refusing to replace a directory without a FileForge workspace marker.')
            shutil.rmtree(OUTPUT)
        shutil.copytree(prepared, OUTPUT)
        verify()
        print(f"Prepared {PIN['task_count']} workspace tasks; {len(entries)} local files, {sum(entry['bytes'] for entry in entries)/1e6:.1f} MB.")


if __name__ == '__main__':
    main()
