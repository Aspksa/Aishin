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
from selenium.webdriver.common.keys import Keys
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


def assert_scope_and_modules(driver: webdriver.Chrome) -> None:
    wait = WebDriverWait(driver, 20)
    scope = driver.find_element(By.ID, "scope-select")
    driver.execute_script(
        """
        const select = arguments[0];
        select.value = 'project:aishin';
        select.dispatchEvent(new Event('change', {bubbles: true}));
        """,
        scope,
    )
    wait.until(
        lambda d: (
            d.find_element(By.ID, "scope-context-label").text.strip()
            == "ПРОЕКТНОЕ ПРОСТРАНСТВО · AISHIN"
        )
    )
    stored = driver.execute_script(
        "return localStorage.getItem('aishin.scope');"
    )
    if stored != "project:aishin":
        raise RuntimeError(
            f"Scope switch was not persisted: {stored!r}"
        )

    result = driver.execute_async_script(
        """
        const done = arguments[0];
        const lines = [];
        for (let i = 1; i <= 24; i++) {
          lines.push(
            "Пункт " + i +
            ": документ browser QA проверяет provenance, " +
            "scope, факты и доступность интерфейса."
          );
        }
        const text =
          "BROWSER QA DOCUMENT\\n" +
          "Параметр: 42 единицы\\n" +
          "Дата: 03.10.2026\\n" +
          lines.join("\\n");
        const file = new File(
          [text],
          "Browser QA 2026.txt",
          {type: "text/plain"}
        );
        const form = new FormData();
        form.append("file", file, file.name);
        form.append("scope", "project:aishin");
        form.append("enrich_with_ai", "false");
        form.append("build_semantic_index", "false");
        fetch("/api/assistant/documents/upload", {
          method: "POST",
          body: form
        })
          .then(async response => {
            const body = await response.json().catch(() => ({}));
            if (!response.ok) {
              throw new Error(body.detail || ("HTTP " + response.status));
            }
            done({ok: true, body: body});
          })
          .catch(error => done({ok: false, error: String(error)}));
        """
    )
    if not result or not result.get("ok"):
        raise RuntimeError(
            "Browser could not seed scoped document: "
            f"{result}"
        )

    documents_nav = driver.find_element(
        By.CSS_SELECTOR, '[data-module="documents"]'
    )
    driver.execute_script("arguments[0].click();", documents_nav)
    wait.until(
        lambda d: (
            "active"
            in (
                d.find_element(
                    By.ID, "documents-module"
                ).get_attribute("class")
                or ""
            )
        )
    )
    wait.until(
        lambda d: len(
            d.find_elements(
                By.CSS_SELECTOR,
                "#documents-list [data-document-open]",
            )
        ) >= 1
    )

    open_button = driver.find_elements(
        By.CSS_SELECTOR,
        "#documents-list [data-document-open]",
    )[0]
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});",
        open_button,
    )
    open_button.click()

    modal = driver.find_element(By.ID, "documents-modal")
    wait.until(
        lambda d: (
            modal.get_attribute("aria-hidden") == "false"
            and "open" in (modal.get_attribute("class") or "")
        )
    )
    active_id = driver.execute_script(
        "return document.activeElement && document.activeElement.id;"
    )
    active_class = driver.execute_script(
        "return document.activeElement && document.activeElement.className;"
    )
    if (
        active_id not in {"documents-reprocess", "documents-modal-close"}
        and "documents-modal-card" not in str(active_class or "")
    ):
        raise RuntimeError(
            "Document dialog did not receive keyboard focus."
        )

    close_button = driver.find_element(By.ID, "documents-modal-close")
    driver.execute_script("arguments[0].focus();", close_button)
    close_button.send_keys(Keys.TAB)
    cycled_id = driver.execute_script(
        "return document.activeElement && document.activeElement.id;"
    )
    if cycled_id != "documents-reprocess":
        raise RuntimeError(
            "Document dialog focus trap did not cycle Tab to first control: "
            f"{cycled_id!r}"
        )

    driver.switch_to.active_element.send_keys(Keys.ESCAPE)
    wait.until(
        lambda d: modal.get_attribute("aria-hidden") == "true"
    )
    returned = driver.execute_script(
        """
        return document.activeElement &&
          document.activeElement.hasAttribute('data-document-open');
        """
    )
    if not returned:
        raise RuntimeError(
            "Closing document dialog did not restore trigger focus."
        )

    research_nav = driver.find_element(
        By.CSS_SELECTOR, '[data-module="research"]'
    )
    driver.execute_script("arguments[0].click();", research_nav)
    wait.until(
        lambda d: (
            "active"
            in (
                d.find_element(
                    By.ID, "research-module"
                ).get_attribute("class")
                or ""
            )
        )
    )
    wait.until(
        lambda d: d.find_element(
            By.ID, "research-score"
        ).is_displayed()
    )


def assert_mobile(driver: webdriver.Chrome) -> None:
    # Use Chrome's real mobile viewport emulation instead of merely narrowing
    # a desktop window. A desktop vertical scrollbar consumes ~15 CSS px and
    # can create a false horizontal-overflow signal at narrow widths.
    driver.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {
            "width": 390,
            "height": 844,
            "deviceScaleFactor": 1,
            "mobile": True,
        },
    )
    driver.get(f"{BASE_URL}/#technical-brain")
    wait_for_observatory(driver)
    time.sleep(0.5)

    metrics = driver.execute_script(
        """
        const topology = document.querySelector('.live-brain-topology');
        const panel = topology?.closest('.live-brain-panel');
        return {
          inner: window.innerWidth,
          client: document.documentElement.clientWidth,
          scroll: document.documentElement.scrollWidth,
          bodyScroll: document.body.scrollWidth,
          panelScroll: panel?.scrollWidth || 0,
          panelClient: panel?.clientWidth || 0,
          topologyWidth: topology?.getBoundingClientRect().width || 0
        };
        """
    )
    if int(metrics["client"]) != 390:
        raise RuntimeError(
            "Chrome mobile emulation did not produce the requested "
            f"390px CSS viewport: {metrics}"
        )
    if int(metrics["scroll"]) > int(metrics["client"]) + 2:
        raise RuntimeError(
            "Mobile page has document-level horizontal overflow: "
            f"{metrics}"
        )
    if int(metrics["bodyScroll"]) > int(metrics["client"]) + 2:
        raise RuntimeError(
            "Mobile body has horizontal overflow: "
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

    # The inspector must remain available and usable in mobile mode too.
    nodes = driver.find_elements(
        By.CSS_SELECTOR, "[data-flow-node-id]"
    )
    if not nodes:
        raise RuntimeError("Mobile topology rendered no interactive nodes.")
    driver.execute_script(
        """
        arguments[0].dispatchEvent(
          new MouseEvent('click', {bubbles: true, cancelable: true})
        );
        """,
        nodes[-1],
    )
    inspector = driver.find_element(By.ID, "lb-node-inspector")
    if not inspector.is_displayed() or not inspector.text.strip():
        raise RuntimeError(
            "Mobile brain node inspector is not visible after interaction."
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
            assert_scope_and_modules(driver)

            driver.get(f"{BASE_URL}/#technical-brain")
            wait_for_observatory(driver)

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
            mobile_overview = (
                ARTIFACTS / "mobile-overview-390x844.png"
            )
            if not driver.save_screenshot(str(mobile_overview)):
                raise RuntimeError(
                    "Mobile overview screenshot was not created."
                )
            if mobile_overview.stat().st_size < 8_000:
                raise RuntimeError(
                    "Mobile overview screenshot is unexpectedly small."
                )

            topology = driver.find_element(
                By.ID, "live-brain-topology"
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                topology,
            )
            time.sleep(0.35)
            mobile_map = (
                ARTIFACTS / "mobile-brain-map-390x844.png"
            )
            if not driver.save_screenshot(str(mobile_map)):
                raise RuntimeError(
                    "Mobile brain-map screenshot was not created."
                )
            if mobile_map.stat().st_size < 8_000:
                raise RuntimeError(
                    "Mobile brain-map screenshot is unexpectedly small."
                )

            print(
                "BROWSER UI SMOKE OK: real Chrome verified Live Brain, "
                "scope isolation, Documents dialog keyboard behavior, "
                "Research routing and mobile containment"
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
