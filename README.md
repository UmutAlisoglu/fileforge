# FileForge

Everyday file tools for Windows, with processing on your own computer. **Version 0.2.0** adds background removal, SVG tracing, image cropping, PDF page exports and PDF organisation, plus batch image conversion.

Prefer to open a tool without installing an application? Use the [FileForge browser edition](https://alisoglu.com/tools/). It processes files on the visitor's device and has its own source code in the [website repository](https://github.com/UmutAlisoglu/umutalisoglu.github.io). This repository builds the Windows application.

## Install the Windows application

Download and extract **FileForge-Windows.zip** from [GitHub Releases](https://github.com/UmutAlisoglu/fileforge/releases). Keep the extracted files together.

Open **install.cmd** to install FileForge for your Windows user, add a Start menu shortcut, and open the app. Administrator rights and Python are not required for the built executable. You can also run **FileForge.exe** directly from the extracted folder. The installer registers FileForge in Windows Installed Apps; use that entry to uninstall, or run the installed uninstall.ps1.

Microsoft Edge **WebView2 Runtime** is required for the native window. Video compression additionally needs **FFmpeg and FFprobe on PATH**. FFmpeg is installed separately and is not included in the ZIP. The other tools work without FFmpeg.

The background removal model is bundled in the application, so it works offline without downloading weights or contacting an AI service. Background removal, SVG tracing and PDF rendering make this release larger than 0.1.0.

## Nine tools

| Tool | Input | Output |
| --- | --- | --- |
| Video compression | MP4, MOV, MKV, WebM, AVI, M4V | H.264 MP4 under a chosen maximum size in decimal MB |
| Excel to PDF | XLSX, UTF-8 CSV | A4 PDF tables, portrait or landscape |
| Image conversion | PNG, JPG, WebP, BMP, TIFF, GIF; up to 50 files | JPG, PNG, WebP or PDF, with optional resize; batch downloads |
| Merge PDFs | 2–20 unlocked PDFs | One PDF in the selected order |
| Remove background | A supported image with one distinct subject | PNG with a transparent or white background |
| Image to SVG | A supported raster image | SVG vector paths with colour and detail controls |
| Crop image | A supported image | PNG, JPG or WebP cropped to the selected rectangle |
| PDF to images | An unlocked PDF | Selected pages as PNG/JPG, packaged as a ZIP when needed |
| Organise PDF pages | Unlocked PDFs | One PDF with selected pages reordered and rotated |

Video uses two-pass encoding, verifies actual output bytes, and retries at a lower bitrate when needed. If a target cannot be met, the job fails with a useful message. It keeps the full duration and can optionally remove audio. Very small targets reduce quality.

Spreadsheet export creates PDF tables. It includes visible worksheet data, repeats the first data row on each page, and splits wide tables into groups of columns. Charts, embedded images, merged cells and Excel print formatting are not preserved. Saved formula results are used; formulas without saved results appear as formula text with a warning. Legacy `.xls` is not supported.

Image conversion preserves aspect ratio, uses white behind transparent pixels for JPG/PDF, removes metadata, and converts the first frame of animations. Background removal uses a compact U²-Net model: a clear foreground subject works best, and fine hair, transparency and busy backgrounds may need further editing. SVG tracing works best for logos, icons and illustrations; photographs become an approximation and may produce large SVGs. SVG output contains vector paths, so it can be scaled without embedding the original photograph.

PDF organisation retains selected source pages instead of rebuilding them from pictures. PDF to images renders pages into pixels. These operations have different results; choose PDF organisation to keep the document as a PDF. Password-protected files need an unlocked copy. Editing can affect signatures and interactive features, so keep the source document.

## Browser or desktop?

| Task or feature | [Browser edition](https://alisoglu.com/tools/) | Windows 0.2.0 |
| --- | --- | --- |
| Convert/resize images and image to PDF | Yes; batch downloads | Yes; batch downloads |
| Remove backgrounds and trace SVGs | Yes; engine/model loads when needed | Yes; engine and model included |
| Crop images | Visual selection and exact dimensions | Visual selection, ratio presets and exact dimensions |
| Merge, reorder and rotate PDF pages | Yes | Yes |
| Export PDF pages as images | Yes | Yes |
| Spreadsheet table to PDF | XLSX, UTF-8 CSV | XLSX, UTF-8 CSV |
| Compress video | Browser engine, up to 100 MB per file | Installed FFmpeg/FFprobe, up to 2 GB per file |
| Installation | Open a page | Extract ZIP; optional per-user installation |
| Processing | Browser memory/workers on your device | Python/native engines on your device |
| Hosting or paid processing account | None required by the visitor | None required |

The two editions use separate implementations and can have different controls, limits and output. New website features do not change an already downloaded Windows executable. See each tool's displayed limits before selecting large files.

## Local files and limits

The interface communicates with a service bound to `127.0.0.1` on your own computer. Selecting files copies them into a temporary job folder on that same computer. There are no accounts, external conversion APIs, remote fonts or cloud uploads. Source files are never modified.

Temporary source copies are deleted when a job finishes, fails or is cancelled. Results expire after 24 hours while the app runs; old temporary directories are also cleaned on startup. **Clear completed** removes retained results immediately. Conversion history belongs to the current application session, so save results before closing the app. Closing the window cancels unfinished jobs. Files you download or save remain until you delete them yourself.

Two jobs run at a time, with up to eight active or queued jobs. Limits include:

- Video: 2 GB per file; encoding has a two-hour time limit.
- Spreadsheets: 50 MB; at most 10,000 rows and 80 columns per visible sheet. Oversized tables are rejected.
- Image conversion: up to 50 images, 100 MB per source image and 500 MB of sources per batch; decoded-image limits also apply.
- Cropping: up to 40 megapixels. Background removal: up to 20 megapixels.
- SVG tracing: up to 40 megapixels; the tracing canvas is reduced to a maximum 2,000-pixel long edge, with a 50 MB SVG output limit.
- PDF merging: 250 MB per file, 2,500 merged pages.
- PDF image exports: up to 100 selected pages and 500 MB of generated images before ZIP compression.
- PDF organisation: 1–20 PDFs with up to 200 source pages in total.

Large files still need enough memory and temporary disk space. Limits help prevent an accidental oversized job; they do not guarantee every malformed or complex file can be converted.

## Develop, test and build

Requires Python 3.12 or newer on Windows. Open **run.cmd** for the desktop version. On first run it creates `.venv` and installs dependencies. To update an existing development environment after pulling new source:

```powershell
.venv\Scripts\python -m pip install -r requirements-desktop.txt
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

For a browser preview of the **desktop service**:

```powershell
powershell -ExecutionPolicy Bypass -File run.ps1 -Browser
```

Then visit `http://127.0.0.1:8765`. This preview uses the desktop engines and should not be exposed publicly.

Run conversion tests and build the Windows executable:

```powershell
.venv\Scripts\python -m pytest tests -q
powershell -ExecutionPolicy Bypass -File build.ps1
```

Build outputs appear in `release/`; generated binaries are distributed through Releases and are not committed to the source repository. In a local build, `install.cmd` and `FileForge.exe` are in `release/`. In the downloadable ZIP they are at the top level. Build work can be redirected with `-WorkDirectory`.

For an actual native-window smoke test:

```powershell
release\FileForge.exe --smoke-test C:\path\to\report.json
```

The report checks the rendered interface, nine visible tools, service health and version 0.2.0. It also sends disposable generated files through the packaged crop, SVG and PDF rendering engines, then checks actual result pixels, dimensions and vector paths. Add `--smoke-image C:\path\to\public-subject.jpg` to test the bundled background model with a suitable public fixture. The optional fixture is not packaged with the application. A failed smoke test returns a nonzero exit code; it does not install the app or modify user files.

See [LEARN.md](LEARN.md) for the architecture, adding tools, local verification and publishing a GitHub release. Dependency and model notices are generated in `release/THIRD_PARTY_NOTICES.txt` and shipped beside the executable. Model provenance and license are in [app/models/README.md](app/models/README.md).
