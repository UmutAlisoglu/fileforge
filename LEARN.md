# Learning from FileForge

FileForge has two editions. The [website](https://alisoglu.com/tools/) runs JavaScript engines inside the browser; this repository runs Python and native libraries inside a Windows application. Both process files on the user's device. A website deployment changes what visitors open next time. A desktop update needs a new executable and downloadable release.

## How the desktop application works

1. `desktop.py` starts a local service on an unused `127.0.0.1` port, then opens a WebView2 window showing that address.
2. `app/static/index.html`, `app.js` and `styles.css` provide the interface. JavaScript sends selected files and settings to the local service, polls the job status, and presents downloads.
3. `app/main.py` validates settings, accepts temporary copies of files, manages the job queue, and handles cancellation, result downloads and cleanup.
4. `app/converters.py` and its converter registry dispatch to the conversion engines. Each engine writes to the job's temporary folder, reports progress and checks for cancellation.
5. `build.ps1` packages the interface, Python runtime, conversion libraries and background model into one executable. The installer copies that executable for the current Windows user and creates a shortcut.

`127.0.0.1` means "this computer". It is not an internet server. A file request in the desktop application's developer tools refers to a temporary copy on the user's computer; it is not a cloud upload.

The native libraries cover different jobs: Pillow reads and edits pictures; vtracer creates SVG paths; ONNX Runtime executes the bundled U²-Net background model; pypdf edits document pages; PDFium renders PDF pages; ReportLab builds new PDFs; openpyxl reads workbooks; FFmpeg/FFprobe inspect and encode videos.

## Run the source safely

Install Python 3.12+ and WebView2. Video compression also needs FFmpeg and FFprobe on PATH. Run `run.cmd` from the repository. The launcher creates a private `.venv` so project dependencies do not need to be installed into your global Python environment.

After pulling an update, refresh dependencies explicitly:

```powershell
.venv\Scripts\python -m pip install -r requirements-desktop.txt
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

You can inspect the interface in a browser while keeping the Python engines:

```powershell
powershell -ExecutionPolicy Bypass -File run.ps1 -Browser
```

Open `http://127.0.0.1:8765`. Keep the service on the loopback address. No router configuration, hosting account or paid API is required.

## Add another tool

Start with one real input/output example: what is selected, which settings matter, and what should the downloaded result contain?

1. Write an engine that accepts the job's source paths and settings, writes its result into the job directory, and returns the result path. Keep source files unchanged. Report progress and check cancellation between expensive steps.
2. Register its key in `CONVERTERS`. Add supported extensions, size/count limits and setting validation in `app/main.py`.
3. Add a tool card and accessible settings controls in `app/static/app.js`. Use the same key as the backend. Validate inputs in both places: the UI helps the user, and the service enforces the rules.
4. If a new runtime package is needed, add it to `requirements.txt`. Add its native resources to `build.ps1` when necessary and include its notices in `tools/third_party_notices.py`.
5. Test a real successful export, invalid files/options, cancellation and the limits that protect memory or disk usage. Open the built executable too: a source test cannot show that a required DLL was missing from the ZIP.

Background removal illustrates this process. Its model lives in `app/models/`, with its source link, checksum and license. The build checks that checksum and bundles the weights. Processing stays offline; the model is loaded from the packaged application instead of being downloaded during a conversion.

## Verify a change

```powershell
.venv\Scripts\python -m pytest tests -q
powershell -ExecutionPolicy Bypass -File build.ps1
```

The tests create disposable fixtures. Keep that approach when adding tests rather than depending on personal documents or photographs.

Check actual output files. A PNG should have the intended dimensions/transparency; an SVG should contain paths; a PDF should contain the expected pages; a ZIP should extract with sensible names. For video compression, compare the finished file's bytes with the requested maximum and inspect its duration. Test the Cancel button during a meaningful job.

Run the native smoke test from a process that can observe its exit code:

```powershell
$smokeReport = Join-Path $PWD '.build/native-smoke.json'
$smokeProcess = Start-Process -FilePath (Join-Path $PWD 'release/FileForge.exe') -ArgumentList @('--smoke-test', ('"' + $smokeReport + '"')) -WindowStyle Hidden -PassThru -Wait
Get-Content -LiteralPath $smokeReport
if ($smokeProcess.ExitCode -ne 0) { throw 'The native application smoke test failed.' }
```

The executable opens its real WebView2 interface and checks the nine tool cards and service version. It then submits disposable generated files to its own job service and checks the packaged crop, SVG tracing and PDF rendering engines. The JSON report records actual dimensions, pixels and SVG paths. Add `--smoke-image C:\path\to\public-subject.jpg` to include a suitable public photo and verify foreground retention and background transparency using the bundled model. That optional fixture is not shipped. Test jobs and outputs are removed before the window closes.

The smoke test does not install the application. If WebView2 is absent, the service cannot start or a packaged conversion engine is missing, the report explains the failure. `multiprocessing.freeze_support()` runs before the desktop CLI because the isolated SVG worker may launch a child copy of the frozen executable; otherwise that child could open a second application window instead of running its conversion.

## Build and distribute

The executable embeds Python, so visitors do not need a Python installation. PyInstaller's `--onefile` format extracts its runtime to a temporary location when launched. New image and PDF engines add native binaries; excluding NumPy would break background removal. `build.ps1` includes the required engines and keeps unrelated GUI/scientific packages excluded.

The `release/` folder should contain:

- `FileForge.exe`
- `install.cmd` and `install.ps1`
- `uninstall.ps1`
- `THIRD_PARTY_NOTICES.txt`

Zip those files at the archive root so the installer stays beside the executable. Do not zip `.venv`, user documents, the whole checkout or build caches. Do not commit generated executables to Git; attach them to a GitHub Release.

## Publish an update on GitHub

Before release, keep the version consistent in the service health response, `desktop.py`, installer metadata, README and generated notices. Run the tests and built-application checks, record the archive checksum, and confirm the downloadable ZIP contains the installer and notices.

The GitHub test workflow runs the Python conversion checks on Windows after pushes and pull requests. `tools/prepare_test_fixture.py` downloads one public U²-Net example, verifies its checksum and puts it inside ignored `.qa/fixtures/`. Run it before tests to include the real-photo background checks. No test reads an image from another checkout. `requirements-lock-windows.txt` records the exact environment used for this Windows release; the main requirements files remain the normal installation entry point.

Commit and push the source changes, then create a tag such as `v0.2.0` for that tested commit. Upload `FileForge-Windows.zip` as a release asset using GitHub's Releases page or `gh release create` with a release-notes file. Release notes should describe the finished features, their limits, requirements such as WebView2/FFmpeg, and the validation actually performed.

After uploading, download that exact asset into a temporary verification folder, check its checksum, extract it, and run its native smoke test. Publishing a release is complete only when someone can download the intended files and launch them.

Finally, update the website's Downloads page and FileForge project guide with the new release link, version, size and feature comparison. Existing installed copies stay on their old version until the user downloads and installs the update.
