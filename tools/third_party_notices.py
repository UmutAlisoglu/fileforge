"""Collect runtime licenses, native-library notices and the bundled model credit."""
from importlib import metadata
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = [
    "fastapi", "starlette", "uvicorn", "python-multipart", "pillow", "openpyxl",
    "et-xmlfile", "reportlab", "pypdf", "pywebview", "pythonnet", "clr-loader",
    "cffi", "pycparser", "bottle", "proxy-tools", "pydantic", "pydantic-core",
    "annotated-types", "annotated-doc", "typing-extensions", "typing-inspection",
    "anyio", "h11", "click", "idna", "opentelemetry-api", "cryptography", "lxml",
    "charset-normalizer", "tzdata", "setuptools", "packaging", "numpy", "onnxruntime",
    "vtracer", "pypdfium2", "flatbuffers", "protobuf", "coloredlogs", "humanfriendly",
    "sympy", "mpmath",
]


def is_notice(item):
    """Wheels may keep native-library licenses outside their dist-info folder."""
    lowered = str(item).replace("\\", "/").lower()
    name = item.name.lower()
    return (
        any(word in name for word in ("license", "licence", "copying", "notice"))
        or "/licenses/" in lowered or "/licences/" in lowered
    ) and Path(name).suffix not in {".py", ".pyc", ".pyd", ".dll", ".so", ".a"}


def main():
    blocks = [
        "FileForge 0.2.0 - Third-party notices\n\n"
        "FFmpeg and FFprobe are separately installed external tools and are not bundled.\n"
        "The following notices cover the Python runtime, conversion libraries and native components distributed in this release.\n"
    ]
    for name in PACKAGES:
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        license_name = distribution.metadata.get("License-Expression") or distribution.metadata.get("License") or "See notice below."
        blocks.append(f"\n{'=' * 72}\n{name} {distribution.version}\nLicense: {license_name}\n")
        seen = set()
        for item in distribution.files or []:
            if not is_notice(item):
                continue
            path = distribution.locate_file(item)
            if path.is_file() and path not in seen:
                seen.add(path)
                blocks.append(f"\n{item}\n{path.read_text(encoding='utf-8', errors='replace')}\n")

    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        blocks.append("\nPython runtime\n" + python_license.read_text(encoding="utf-8", errors="replace"))

    model_directory = ROOT / "app/models"
    blocks.append(f"\n{'=' * 72}\nU²-Net small / U2NETP background removal model\n")
    for filename in ("README.md", "LICENSE.txt"):
        path = model_directory / filename
        if not path.is_file():
            raise RuntimeError(f"The bundled model notice is missing: {path}")
        blocks.append(f"\n{filename}\n{path.read_text(encoding='utf-8')}\n")

    output_directory = ROOT / "release"
    output_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "THIRD_PARTY_NOTICES.txt").write_text("\n".join(blocks), encoding="utf-8")


if __name__ == "__main__":
    main()
