# FileForge

Local file tools for Windows. **Version 0.3.0** brings the connected FileForge workspace into the desktop application, with its engines bundled for offline use. The existing native converters remain available for larger files.

## Install or update

Download **FileForge-Windows.zip** for Windows x64 from [GitHub Releases](https://github.com/UmutAlisoglu/fileforge/releases). Extract the entire ZIP, close any running copy of FileForge, and open **install.cmd**. This installs the update for your Windows user and adds a Start menu shortcut. No administrator rights, Python or Node.js are needed.

For portable use, open **FileForge.exe** from the extracted folder. **Keep the `workspace` folder beside the executable.** It contains the local engines, fonts, language data and licenses. Copying only the executable is not a complete installation.

Microsoft Edge **WebView2 Runtime** is required for the window. Native video conversion also needs separately installed **FFmpeg and FFprobe on PATH**. The workspace's short-video engine is included and does not need that installation.

Uninstall through Windows Installed Apps, or run the installed uninstall.ps1. Downloaded results are your files and remain where you saved them.

## Connected workspace

The application opens in the connected workspace. Choose a file, pick a compatible action, review the result and continue into another tool without downloading and selecting the result again. **All tools** also includes a format picker, task search and practical limits.

| Area | Included workspace tools |
| --- | --- |
| Office and documents | Word DOCX → PDF, PowerPoint PPTX → PDF, text → PDF, PDF → text, Excel/CSV → PDF, CSV ↔ JSON |
| PDFs | Merge, organise/reorder/rotate, split, image-based compression, pages → images, images → PDF |
| Images | Convert/resize/batch, HEIC → JPG, crop, background removal with mask editing, SVG tracing, metadata removal |
| Scans and text | Four-corner document scanning and cleanup; OCR in English, German and Turkish |
| Sharing | Screenshot studio with frames, backgrounds, captions and exact-size exports |
| Video | Local short-video compression to MP4 |

There are 22 task entries across 21 tool pages; Images → PDF shares Image studio. The models, Office engines, OCR language data, fonts, HEIC decoder and FFmpeg WebAssembly engine are included. They are loaded from this computer when needed, not from a CDN or conversion service.

Office inputs are limited to **10 MB and 20 pages/slides**. Exports contain flattened page images; fonts, page breaks and complex layouts can differ from Microsoft Office. Review the preview. Legacy DOC/PPT files, macros and embedded objects are not supported. Text → PDF preserves selectable text; OCR produces editable TXT, not a searchable PDF.

Other workspace limits include 20 MB images, 25 MB PDFs, 10 MB spreadsheets and 100 MB short videos, with additional page, decoded-image and batch limits displayed in each tool. Large or malformed files may need a smaller input. PDF compression reduces supported JPEG images; text-only PDFs may not shrink.

## Native tools for larger files

Choose **Native tools** in the header to use the existing Python/native job service:

| Tool | Native capability |
| --- | --- |
| Video compression | Two-pass H.264 MP4 with verified byte targets; inputs up to 2 GB; installed FFmpeg/FFprobe required |
| Excel to PDF | XLSX or UTF-8 CSV up to 50 MB; A4 PDF tables, not Excel print layouts |
| Image conversion | JPG/PNG/WebP/PDF, resize and batches of up to 50 images; TIFF input supported |
| Background removal | Bundled U²-Net small model; transparent or white PNG |
| SVG tracing | Native vtracer with colour/detail controls |
| Cropping | Visual and exact pixel selection; PNG/JPG/WebP |
| PDF to images | Native PDFium; selected PNG/JPG pages or ZIP |
| PDF organisation | Preview, select, reorder and rotate source pages |
| Merge PDFs | Combine unlocked documents in the chosen order |

Native image inputs can be up to 100 MB each/500 MB per batch, with decoded-image limits. PDF inputs can be up to 250 MB, with tool-specific page limits. Two jobs run at once, with up to eight active or queued jobs. Each interface shows its own limits; switching modes does not transfer an unfinished job automatically.

## File handling

- The service listens only on **127.0.0.1**, meaning this computer. No account, cloud upload, conversion API or analytics is required.
- Workspace files and results live in the current page's memory. Download before navigating away or closing the app. **Clear all** releases the selection and previews. Optional settings/favourites store choices, not documents; the private WebView session clears storage when the app closes.
- Native tools make temporary source copies on this computer. Copies are deleted after a job completes, fails or is cancelled. Results expire after 24 hours while the service runs; old folders are also cleaned on startup. **Clear completed** removes retained native results immediately.
- Source files are never modified. Files you save remain until you remove them yourself. Closing the app cancels unfinished native jobs.

See **Help** inside the app for the two modes, requirements and component notices.

## Source, tests and Windows builds

The Windows release is tested with Python 3.14, Node.js 24 and WebView2. Create a private environment, then prepare the pinned workspace:

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-desktop.txt -r requirements-dev.txt
.venv\Scripts\python tools/prepare_workspace.py
.venv\Scripts\python tools/prepare_test_fixture.py
.venv\Scripts\python -m pytest tests -q
powershell -NoProfile -ExecutionPolicy Bypass -File build.ps1
```

`workspace-source.json` pins the exact [website source](https://github.com/UmutAlisoglu/umutalisoglu.github.io) revision. The builder archives that commit, applies desktop navigation, removes website/offline-install controls and copies only tool runtimes and assets. Uncommitted website changes and visitor files are not included. Use `--source C:\path\to\website` to read that commit from an existing Git repository instead of cloning it. `--verify` checks the generated file manifest before packaging.

The build emits `release/FileForge.exe`, installers, notices and `release/workspace/`. Workspace modules remain ordinary replaceable files, including LGPL components. Generated runtimes, build caches and executables are not committed. Runtime licenses and corresponding-source links ship in `workspace/licenses/`, `workspace/THIRD_PARTY_NOTICES.md`, `workspace/SOURCE.md` and the main notices file.

To test the actual executable, run it with `--smoke-test C:\path\to\report.json`. The window checks its local service, nine native tool entries, the connected workspace, actual native crop/SVG/PDF output, and Word/PowerPoint/text/CSV exports in WebView2. Add `--smoke-image C:\path\to\public-subject.jpg` for a real bundled-model background check or `--smoke-heic C:\path\to\public-example.heic` for native-window HEIC decoding. All fixtures are disposable and no app installation is performed.

See [LEARN.md](LEARN.md) for architecture and release verification. Updating the live website does **not** silently update an installed desktop copy; each desktop release packages a tested source revision.
