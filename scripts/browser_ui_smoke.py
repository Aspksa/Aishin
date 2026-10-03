from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "browser-smoke"
HOST = "127.0.0.1"
PORT = 8765
BASE_URL = f"http://{HOST}:{PORT}"


def browser_binary() -> str | None:
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
    return None


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


def create_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--force-device-scale-factor=1")
    options.add_argument("--window-size=1440,1000")

    binary = browser_binary()
    if binary:
        options.binary_location = binary

    driver_binary = shutil.which("chromedriver")
    service = (
        Service(executable_path=driver_binary)
        if driver_binary
        else Service()
    )
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(15)
    return driver


def wait_for_observatory(driver: webdriver.Chrome) -> None:
    wait = WebDriverWait(driver, 25)
    wait.until(
        lambda d: d.find_element(
            By.ID, "live-brain-observatory"
        ).is_displayed()
    )
    wait.until(
        lambda d: len(
            d.find_elements(By.CSS_SELECTOR, "[data-flow-node-id]")
        ) >= 20
    )
    wait.until(
        lambda d: d.find_element(
            By.ID, "lb-node-inspector"
        ).is_displayed()
    )


def assert_desktop(driver: webdriver.Chrome) -> None:
    details = driver.find_element(By.ID, "technical-brain")
    if details.get_attribute("open") is None:
        raise RuntimeError(
            "#technical-brain deep link did not open diagnostics."
        )

    source = driver.page_source
    for marker in (
        "Нейронная обсерватория Айшин",
        "Нервная карта выполнения",
        "brain-flow-legend",
        'id="lb-node-inspector"',
        "AISHIN 00.00.12 · REAL-TIME BRAIN",
    ):
        if marker not in source:
            raise RuntimeError(
                f"Dynamic browser DOM marker missing: {marker}"
            )

    nodes = driver.find_elements(
        By.CSS_SELECTOR, "[data-flow-node-id]"
    )
    if len(nodes) < 20:
        raise RuntimeError(
            f"Brain topology rendered only {len(nodes)} nodes."
        )

    # Verify the map is actually interactive, not only decorative SVG.
    first = nodes[0]
    first_label = first.get_attribute("aria-label") or ""
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});",
        first,
    )
    first.click()
    inspector = driver.find_element(By.ID, "lb-node-inspector")
    inspector_text = inspector.text.strip()
    if not inspector_text or (
        "Выберите узел" in inspector_text
    ):
        raise RuntimeError(
            "Brain node click did not update the inspector."
        )
    if first_label:
        label_head = first_label.split("·", 1)[0].strip()
        if label_head and label_head not in inspector_text:
            raise RuntimeError(
                "Inspector does not describe the selected node."
            )


def assert_mobile(driver: webdriver.Chrome) -> None:
    driver.set_window_size(390, 844)
    time.sleep(0.6)
    metrics = driver.execute_script(
        """
        return {
          client: document.documentElement.clientWidth,
          scroll: document.documentElement.scrollWidth,
          panelScroll: document.querySelector(
            '.live-brain-panel:has(.live-brain-topology)'
          )?.scrollWidth || 0,
          panelClient: document.querySelector(
            '.live-brain-panel:has(.live-brain-topology)'
          )?.clientWidth || 0
        };
        """
    )
    if int(metrics["scroll"]) > int(metrics["client"]) + 4:
        raise RuntimeError(
            "Mobile page has document-level horizontal overflow: "
            f"{metrics}"
        )
    if (
        int(metrics["panelScroll"]) > 0
        and int(metrics["panelClient"]) > 0
        and int(metrics["panelScroll"]) <= int(metrics["panelClient"])
    ):
        raise RuntimeError(
            "Mobile topology should preserve readable width inside "
            "its own scroll container."
        )


def main() -> int:
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

        driver: webdriver.Chrome | None = None
        try:
            wait_for_server()
            driver = create_driver()
            driver.get(f"{BASE_URL}/#technical-brain")
            wait_for_observatory(driver)
            assert_desktop(driver)

            desktop = ARTIFACTS / "desktop-1440x1000.png"
            if not driver.save_screenshot(str(desktop)):
                raise RuntimeError("Desktop screenshot was not created.")
            if desktop.stat().st_size < 10_000:
                raise RuntimeError(
                    "Desktop screenshot is unexpectedly small."
                )

            (ARTIFACTS / "desktop-dom.html").write_text(
                driver.page_source,
                encoding="utf-8",
            )

            assert_mobile(driver)
            mobile = ARTIFACTS / "mobile-390x844.png"
            if not driver.save_screenshot(str(mobile)):
                raise RuntimeError("Mobile screenshot was not created.")
            if mobile.stat().st_size < 8_000:
                raise RuntimeError(
                    "Mobile screenshot is unexpectedly small."
                )

            print(
                "BROWSER UI SMOKE OK: real Chrome rendered expanded "
                "Live Brain; interaction and mobile containment verified"
            )
            return 0
        finally:
            if driver is not None:
                driver.quit()
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
