"""Package only tested public application files, never the working checkout."""
import hashlib
from pathlib import Path
import zipfile

if __package__:
    from .prepare_workspace import verify, PIN
else:
    from prepare_workspace import verify, PIN

ROOT = Path(__file__).resolve().parents[1]


def main():
    release = ROOT / 'release'
    required = ['FileForge.exe', 'install.cmd', 'install.ps1', 'uninstall.ps1', 'THIRD_PARTY_NOTICES.txt']
    for name in required:
        if not (release / name).is_file():
            raise RuntimeError(f'Build the executable and installer first: missing {name}')
    manifest = verify(release / 'workspace')
    files = [(release / name, name) for name in required]
    files += [(release / 'workspace' / item['path'], 'workspace/' + item['path']) for item in manifest['files']]
    files.append((release / 'workspace/workspace-manifest.json', 'workspace/workspace-manifest.json'))
    output = ROOT / '.build'
    output.mkdir(exist_ok=True)
    archive = output / 'FileForge-Windows.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for file, name in files:
            package.write(file, name)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / 'SHA256SUMS.txt').write_text(f'{checksum}  FileForge-Windows.zip\n', encoding='ascii')
    print(f"FileForge {PIN['version']}: {archive.stat().st_size} bytes; {len(files)} files; SHA-256 {checksum}")


if __name__ == '__main__':
    main()
