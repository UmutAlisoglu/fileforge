"""Native Windows shell around FileForge's local conversion service."""
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

VERSION = "0.2.0"
EXPECTED_TOOLS = 9


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", metavar="REPORT", help="Open the actual native window, verify it, then close.")
    parser.add_argument("--smoke-image", metavar="IMAGE", help="An optional public subject image for the smoke test's bundled background model check.")
    args = parser.parse_args()
    # PyInstaller's windowed bootloader provides no stdout/stderr handles.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    import uvicorn
    import webview
    from app.main import app

    log_dir = Path(os.environ.get("TEMP", ".")) / "fileforge-logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(filename=log_dir / "desktop.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    logging.info("Serving FileForge at %s", url)
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("The local conversion service could not start.")
    webview.settings["ALLOW_DOWNLOADS"] = True
    window = webview.create_window("FileForge", url, width=1280, height=920,
                                   min_size=(840, 640), background_color="#f4f5f0")

    smoke_result = {"ok": False, "version": VERSION}
    smoke_done = threading.Event()
    if args.smoke_test:
        report_path = Path(args.smoke_test).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(smoke_result, indent=2), encoding="utf-8")

        def inspect():
            report = {"version": VERSION}
            try:
                with urllib.request.urlopen(url + "/api/health", timeout=10) as response:
                    report["health"] = json.load(response)
                report["title"] = window.evaluate_js("document.title")
                report["tools"] = window.evaluate_js("document.querySelectorAll('#tool-grid button').length")
                report["body"] = window.evaluate_js("document.querySelector('h1').textContent")
                from tools.frozen_checks import run_checks
                report["conversions"] = run_checks(url, args.smoke_image)
                report["ok"] = (
                    report["tools"] == EXPECTED_TOOLS
                    and report["health"]["status"] == "ok"
                    and report["health"].get("version") == VERSION
                    and "FileForge" in report["title"]
                    and bool(report["conversions"])
                    and all(check["ok"] for check in report["conversions"].values())
                )
                if not report["ok"]:
                    report["error"] = "The native UI, service version or a frozen conversion engine failed its release check."
            except Exception as exc:
                report["ok"] = False
                report["error"] = str(exc)
            finally:
                smoke_result.update(report)
                try:
                    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
                finally:
                    smoke_done.set()
                    window.destroy()
        window.events.loaded += inspect

        def watchdog():
            if not smoke_done.wait(120):
                smoke_result["error"] = "The native interface or conversion checks did not finish within 120 seconds."
                report_path.write_text(json.dumps(smoke_result, indent=2), encoding="utf-8")
                window.destroy()

        threading.Thread(target=watchdog, daemon=True).start()
    try:
        webview.start(gui="edgechromium", private_mode=True)
    finally:
        server.should_exit = True
        thread.join(timeout=15)
    if args.smoke_test:
        if not smoke_done.is_set() and "error" not in smoke_result:
            smoke_result["error"] = "The native window closed before its interface finished loading."
            report_path.write_text(json.dumps(smoke_result, indent=2), encoding="utf-8")
        smoke_done.set()
        return 0 if smoke_result["ok"] else 1
    return 0


if __name__ == "__main__":
    # Frozen native-engine workers must enter their multiprocessing target before
    # starting another FileForge window or parsing the desktop CLI.
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        raise SystemExit(main())
    except Exception as error:
        logging.exception("FileForge startup failed")
        if "--smoke-test" in sys.argv:
            try:
                report_path = Path(sys.argv[sys.argv.index("--smoke-test") + 1]).resolve()
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(json.dumps({"ok": False, "version": VERSION, "error": str(error)}, indent=2), encoding="utf-8")
            finally:
                raise SystemExit(1)
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None, f"FileForge could not start.\n\n{error}\n\nMake sure Microsoft Edge WebView2 Runtime is installed.",
            "FileForge", 0x10,
        )
        raise
