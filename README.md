# FileForge

A Windows desktop application for everyday file conversion. Version 0.1.0.

## Install the built application

Download and extract **FileForge-Windows.zip** from [GitHub Releases](https://github.com/UmutAlisoglu/fileforge/releases). Keep the extracted files together.

Open **release/install.cmd**. It installs FileForge for your Windows user, adds a Start menu shortcut, and opens the app. Administrator rights and Python are not required for the built executable. You can also run **release/FileForge.exe** directly.

In the downloaded ZIP, install.cmd and FileForge.exe are at the top level. In a local build, they are in release/. Generated binaries are distributed through Releases and are not committed to the source repository.

Microsoft Edge WebView2 Runtime is required for the native window. Video compression additionally needs FFmpeg and FFprobe on PATH; these are already installed on the development computer. FFmpeg is not bundled in this first release.

The installer registers FileForge in Windows Installed Apps. Use that entry to uninstall, or run the installed uninstall.ps1. The source folder remains available separately.

## Tools included

| Tool | Input | Output |
| --- | --- | --- |
| Video compression | MP4, MOV, MKV, WebM, AVI, M4V | H.264 MP4 under a chosen maximum size in decimal MB |
| Excel to PDF | XLSX, UTF-8 CSV | A4 PDF tables, portrait or landscape |
| Image conversion | PNG, JPG, WebP, BMP, TIFF, GIF | JPG, PNG, WebP, PDF, optional resize |
| Merge PDFs | 2–20 unlocked PDFs | One PDF in the selected order |

Video uses two-pass encoding, verifies actual output bytes, and retries at a lower bitrate when needed. If a target cannot be met, the job fails with a useful message. It keeps the full duration, and can optionally remove audio. Very small targets reduce quality.

Spreadsheet export is a table export, not a reproduction of Excel's print layout. It includes visible worksheet data, repeats the first data row on each page, and splits wide tables into groups of columns. Charts, embedded images, merged cells and print formatting are not preserved. Saved formula results are used; formulas without saved results appear as formula text with a warning. Legacy .xls is not supported yet.

Image conversion preserves aspect ratio, uses white behind transparent pixels for JPG/PDF, removes metadata, and converts the first frame of animations.

## Local files and limits

The UI communicates only with a service bound to 127.0.0.1 on your own computer. There are no accounts, external APIs, remote fonts or cloud uploads. Source files are never modified.

Temporary uploaded copies are deleted when the job finishes. Results expire after 24 hours while the app runs; old temporary directories are also cleaned on startup. Clear completed removes retained results immediately. Conversion history is scoped to the current app session, so download results before closing the app. Closing the window cancels unfinished jobs.

Two jobs run at a time, with up to eight active/queued jobs. Limits: video 2 GB per file, spreadsheets 50 MB, images 100 MB, PDFs 250 MB each and 2,500 merged pages. Spreadsheet tables are limited to 10,000 rows and 80 columns per visible sheet. Oversized tables are rejected rather than silently truncated.

## Develop

Requires Python 3.12+.

Open run.cmd for the desktop version. On first run, it creates a local .venv and installs dependencies.

For the browser preview:

    powershell -ExecutionPolicy Bypass -File run.ps1 -Browser

Then visit http://127.0.0.1:8765.

The application has four small pieces:

- app/static/: interface and job queue.
- app/main.py: uploads, jobs, cancellation, retention and downloads.
- app/converters.py: conversion engines and converter registry.
- desktop.py: the native Windows window and local service lifecycle.

To add a tool, add an engine to CONVERTERS, its accepted extensions/settings in main.py, and its controls in static/app.js.

## Build and test

    .venv\Scripts\python -m pip install -r requirements-dev.txt
    .venv\Scripts\python -m pytest tests -q
    powershell -ExecutionPolicy Bypass -File build.ps1

Build outputs appear in release/. Build work can be redirected with -WorkDirectory. The build excludes unrelated GUI and scientific libraries.

For a native-window smoke test:

    release\FileForge.exe --smoke-test C:\path\to\report.json

The report checks the actual rendered interface and the conversion service before closing the window.

## Next additions

Audio extraction and conversion, PDF splitting, Word/PowerPoint conversion through an office engine, batch conversion, and exact Excel print-layout export are natural extensions. They are not implemented in this first release.

Technical references: [FFmpeg](https://ffmpeg.org/ffmpeg.html), [FastAPI uploads](https://fastapi.tiangolo.com/tutorial/request-files/), [openpyxl workbook loading](https://openpyxl.readthedocs.io/en/stable/_modules/openpyxl/reader/excel.html), [pywebview](https://pywebview.flowrl.com/guide/usage.html), [PyInstaller](https://pyinstaller.org/en/stable/spec-files.html).
