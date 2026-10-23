# Working on FileForge Desktop

FileForge 0.3.0 combines a connected workspace with the existing native conversion service. Both run on the user's computer. The desktop release includes its engines; the website is not opened remotely inside the app.

## Architecture

1. `desktop.py` starts FastAPI on an unused 127.0.0.1 port, then opens the real WebView2 window. The root opens `/tools/workspace/`. Missing or mismatched workspace files produce an actionable startup error.
2. `tools/prepare_workspace.py` archives the exact website commit in `workspace-source.json`, adapts navigation and builds the static tool runtime. All engines, models, fonts and OCR languages are copied into ignored `app/workspace/`. The manifest records public source provenance and SHA-256 hashes.
3. `app/workspace.py` locates that folder in source or next to the packaged executable. `app/main.py` serves those public assets locally. Nothing proxies visitors' documents to the website.
4. The workspace processes selected files in JavaScript workers and passes results between compatible tools in memory. Its original tool limits, cancellation, Office isolation and archive checks remain in place.
5. `/native/` keeps `app/static/` and the existing job service. `app/converters.py`, `app/advanced_converters.py` and `app/image_batch.py` run Python/native engines for larger inputs. Native source copies, queued jobs and result retention are separate from workspace memory.

The service keeps loopback host and origin checks. Workspace responses allow same-origin workers/iframes and local WebAssembly, with COOP/COEP headers for isolated engines. External runtime connections remain blocked. Only the isolated finish worker receives JavaScript function-generation permission, required by libheif's Embind bindings; pages and the other workers do not.

## Rebuild the workspace

Install Python 3.14 and Node.js 24 on the build machine. Users of the finished app do not need them.

```powershell
.venv\Scripts\python -m pip install -r requirements-desktop.txt -r requirements-dev.txt
.venv\Scripts\python tools/prepare_workspace.py
.venv\Scripts\python tools/prepare_workspace.py --verify
```

For an existing website checkout, use `--source C:\path\to\website`. The builder uses `git archive` on the pinned commit, so it never bundles uncommitted work, credentials or node_modules. It builds in a temporary `.build/` directory. Only a directory with the FileForge workspace marker can be replaced at the fixed generated output path.

Changing `workspace-source.json` is an explicit desktop update. Review that revision, adapt the builder if needed, rebuild, and rerun the checks. Do not fetch new tools or overwrite an installed workspace at runtime. The package's normal modules are replaceable so LGPL engines can be modified by recipients; startup does not reject such modifications based on content hashes. Build-time verification catches accidental source/package drift.

## Verify source and packaged behavior

```powershell
.venv\Scripts\python tools/prepare_test_fixture.py
.venv\Scripts\python -m pytest tests -q
powershell -NoProfile -ExecutionPolicy Bypass -File build.ps1
```

Tests create generated files and a checksum-pinned public background-model fixture. They check actual native output, limits, cancellation, temporary-file cleanup, host/origin protection, workspace completeness and HTTP policies. The CI workflow prepares the pinned workspace before running them.

Run a native smoke test without installing over the user's app:

```powershell
$smokeProcess = Start-Process -FilePath (Join-Path $PWD 'release/FileForge.exe') -ArgumentList @('--smoke-test', '.qa/native-smoke.json', '--smoke-image', '.qa/fixtures/u2net-horse.jpg') -WindowStyle Hidden -PassThru -Wait
Get-Content .qa/native-smoke.json
if ($smokeProcess.ExitCode -ne 0) { throw 'Packaged checks failed.' }
```

The real WebView2 window checks rendered workspace controls and uses disposable DOCX/PPTX fixtures to export actual two-page PDFs with images. Text → PDF is checked for selectable multilingual text; JSON → CSV is checked for real data. Existing native checks validate pixels, dimensions, SVG vector paths and background alpha. The report does not contain user documents. The watchdog prevents an indefinitely hung test.

`tools/browser_smoke.mjs` checks the native interface in Chrome against `http://127.0.0.1:8765`; use `run.ps1 -Browser` for that local preview. Set `FILEFORGE_SITE_ROOT` to a website checkout with Playwright installed when reusing its development dependencies. The website's engine/browser checks can also target this local origin with `TEST_URL`, adjusting website-only navigation assertions for the desktop shell. Browser tools must perform only same-origin GETs and blob operations; only native jobs use local POST requests.

## Package and publish

`build.ps1` verifies the pinned workspace before building. Native Python libraries, the compact background model, UI and smoke fixtures are embedded in FileForge.exe. The workspace remains a separate folder so engines are replaceable and startup need not extract every browser runtime from the executable. All license copies and source references must be retained.

The ZIP contains only these release-root entries:

- `FileForge.exe`
- `workspace/`
- `install.cmd`, `install.ps1`, `uninstall.ps1`
- `THIRD_PARTY_NOTICES.txt`

`tools/package_release.py` verifies the manifest, packages that folder and emits SHA256SUMS.txt. No .venv, repository metadata, build logs or test outputs belong in the ZIP. The installer copies both the executable and workspace into its verified app folder; user documents are never an installation input.

Keep the version consistent in `desktop.py`, `app/main.py`, workspace-source.json, the desktop header adapter, installer, help, notices and README. Commit tested source and publish a versioned GitHub release with the ZIP, checksum and native smoke report. Download the exact uploaded asset into an isolated verification folder, compare its checksum, extract it and run its executable's smoke test. Test installation in a new .qa folder with `-SkipShortcuts -SkipRegistration -SkipLaunch`, not over the user's real installation.

Finally update the website's download URLs, release size/date and feature comparison. Installed copies are updated only when the user downloads and installs the new release.
