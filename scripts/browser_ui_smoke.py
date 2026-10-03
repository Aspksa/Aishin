from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "browser-smoke"
HOST = "127.0.0.1"
PORT = 8765
BASE_URL = f"http://{HOST}:{PORT}"


def browser_binary() -> str:
    candidates = [
        os.getenv("CHROME_BIN", "").strip(),
        shutil.which("google-chrome") or "",
        shutil.which("google-chrome-stable") or "",
        shutil.which("chromium") or "",
        shutil.which("chromium-browser") or "",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
    ]
    for item in candidates:
        if item and Path(item).is_file():
            return item
    raise RuntimeError(
        "Headless Chrome/Chromium not found on CI runner."
    )


def wait_for_server(timeout: float = 35.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{BASE_URL}/health", timeout=2.0) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.35)
    raise RuntimeError(
        f"FastAPI did not become ready: {last_error}"
    )


def run_browser(
    browser: str,
    *,
    width: int,
    height: int,
    name: str,
    dump_dom: bool,
) -> str:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    screenshot = ARTIFACTS / f"{name}.png"
    profile = ARTIFACTS / f"profile-{name}"
    profile.mkdir(parents=True, exist_ok=True)

    args = [
        browser,
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-features=Translate,BackForwardCache",
        "--force-device-scale-factor=1",
        f"--window-size={width},{height}",
        "--virtual-time-budget=9000",
        f"--user-data-dir={profile}",
        f"--screenshot={screenshot}",
    ]
    if dump_dom:
        args.append("--dump-dom")
    args.append(f"{BASE_URL}/#technical-brain")

    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Headless browser failed ({name}): "
            f"exit={result.returncode}\n{result.stderr[-3000:]}"
        )
    if not screenshot.is_file() or screenshot.stat().st_size < 10_000:
        raise RuntimeError(
            f"Browser screenshot {name} is missing or unexpectedly small."
        )
    return result.stdout if dump_dom else ""


def assert_dynamic_dom(dom: str) -> None:
    required = [
        'id="scope-select"',
        'id="live-brain-observatory"',
        'id="live-brain-topology"',
        'id="lb-stream-state"',
        "Нейронная обсерватория Айшин",
        "Нервная карта выполнения",
        "brain-flow-legend",
        "AISHIN 00.00.12 · REAL-TIME BRAIN",
    ]
    missing = [marker for marker in required if marker not in dom]
    if missing:
        raise RuntimeError(
            "Headless browser did not render required dynamic UI: "
            + ", ".join(missing)
        )

    # Dynamic JavaScript must have replaced the initial skeleton.
    if '<div class="live-brain-skeleton">Собираю телеметрию…</div>' in dom:
        raise RuntimeError(
            "Live Brain remained on the initial skeleton after virtual time."
        )

    if "BACKEND НЕ ПОДКЛЮЧЁН" in dom and 'class="module-page active"' in dom:
        raise RuntimeError(
            "The active workspace rendered as a disconnected placeholder."
        )


def main() -> int:
    browser = browser_binary()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    server_log = ARTIFACTS / "uvicorn.log"
    with server_log.open("w", encoding="utf-8") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                HOST,
                "--port",
                str(PORT),
                "--log-level",
                "warning",
            ],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            wait_for_server()
            desktop_dom = run_browser(
                browser,
                width=1440,
                height=1000,
                name="desktop-1440x1000",
                dump_dom=True,
            )
            assert_dynamic_dom(desktop_dom)
            (ARTIFACTS / "desktop-dom.html").write_text(
                desktop_dom,
                encoding="utf-8",
            )

            run_browser(
                browser,
                width=390,
                height=844,
                name="mobile-390x844",
                dump_dom=False,
            )

            print(
                "BROWSER UI SMOKE OK: dynamic Live Brain rendered; "
                "desktop/mobile screenshots created"
            )
            return 0
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
