"""Locate the public workspace files, separately from native job storage."""
import json
from pathlib import Path
import sys

WORKSPACE = (Path(sys.executable).parent / 'workspace') if getattr(sys, 'frozen', False) else Path(__file__).parent / 'workspace'


def workspace_manifest():
    try:
        manifest = json.loads((WORKSPACE / 'workspace-manifest.json').read_text(encoding='utf-8'))
        if manifest.get('project') == 'FileForge workspace' and (WORKSPACE / 'tools/workspace/index.html').is_file():
            return manifest
    except (OSError, ValueError):
        pass
    return None
