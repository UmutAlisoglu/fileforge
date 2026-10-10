"""Collect the installed runtime dependencies' published license notices."""
from importlib import metadata
from pathlib import Path
import sys

packages = [
    "fastapi", "starlette", "uvicorn", "python-multipart", "pillow", "openpyxl",
    "et-xmlfile", "reportlab", "pypdf", "pywebview", "pythonnet", "clr-loader",
    "cffi", "pycparser", "bottle", "proxy-tools", "pydantic", "pydantic-core",
    "annotated-types", "annotated-doc", "typing-extensions", "typing-inspection",
    "anyio", "h11", "click", "idna", "opentelemetry-api", "cryptography", "lxml",
    "charset-normalizer", "tzdata", "setuptools", "packaging",
]
blocks = ["FileForge 0.1.0 - Third-party notices\n\nFFmpeg is a separately installed external tool and is not bundled.\n"]
for name in packages:
    try:
        distribution = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        continue
    license_name = distribution.metadata.get("License-Expression") or distribution.metadata.get("License") or "See notice below."
    blocks.append(f"\n{'=' * 72}\n{name} {distribution.version}\nLicense: {license_name}\n")
    for item in distribution.files or []:
        if ".dist-info" in str(item) and any(word in item.name.lower() for word in ["license", "copying", "notice"]):
            path = distribution.locate_file(item)
            if path.is_file():
                blocks.append(f"\n{item.name}\n{path.read_text(encoding='utf-8', errors='replace')}\n")
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.exists():
    blocks.append("\nPython runtime\n" + python_license.read_text(encoding="utf-8", errors="replace"))
root = Path(__file__).resolve().parents[1]
(root / "release/THIRD_PARTY_NOTICES.txt").write_text("\n".join(blocks), encoding="utf-8")
