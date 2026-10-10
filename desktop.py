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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", metavar="REPORT", help="Open the actual native window, verify it, then close.")
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

    if args.smoke_test:
        def inspect():
            report = {}
            try:
                with urllib.request.urlopen(url + "/api/health", timeout=10) as response:
                    report["health"] = json.load(response)
                report["title"] = window.evaluate_js("document.title")
                report["tools"] = window.evaluate_js("document.querySelectorAll('#tool-grid button').length")
                report["body"] = window.evaluate_js("document.querySelector('h1').textContent")
                report["ok"] = report["tools"] == 4 and report["health"]["status"] == "ok"
            except Exception as exc:
                report["ok"] = False
                report["error"] = str(exc)
            finally:
                Path(args.smoke_test).write_text(json.dumps(report, indent=2), encoding="utf-8")
                window.destroy()
        window.events.loaded += inspect
    try:
        webview.start(gui="edgechromium", private_mode=True)
    finally:
        server.should_exit = True
        thread.join(timeout=15)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        logging.exception("FileForge startup failed")
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None, f"FileForge could not start.\n\n{error}\n\nMake sure Microsoft Edge WebView2 Runtime is installed.",
            "FileForge", 0x10,
        )
        raise
