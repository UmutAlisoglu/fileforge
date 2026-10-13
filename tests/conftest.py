"""Keep disposable conversion checks away from a visitor's desktop job folder."""
import os
from pathlib import Path

os.environ['FILEFORGE_DATA_DIR'] = str(Path(__file__).resolve().parents[1] / '.data-tests' / 'jobs')
