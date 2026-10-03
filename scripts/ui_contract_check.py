from __future__ import annotations

import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app" / "templates" / "index.html"
STATIC = ROOT / "app" / "static"


class UiParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.assets: list[str] = []
        self.attrs_by_id: dict[str, dict[str, str]] = {}

    def handle_starttag(self, tag: str, attrs) -> None:
        data = {str(k): str(v or "") for k, v in attrs}
        element_id = data.get("id")
        if element_id:
            self.ids.append(element_id)
            self.attrs_by_id[element_id] = data
        if tag == "script" and data.get("src"):
            self.assets.append(data["src"])
        if tag == "link" and data.get("href"):
            self.assets.append(data["href"])


def fail(message: str) -> None:
    raise RuntimeError(message)


def main() -> int:
    html = TEMPLATE.read_text(encoding="utf-8")
    parser = UiParser()
    parser.feed(html)

    duplicate_ids = sorted(
        key for key, count in Counter(parser.ids).items() if count > 1
    )
    if duplicate_ids:
        fail(f"Duplicate HTML ids: {duplicate_ids}")

    missing_assets = []
    stale_assets = []
    for asset in parser.assets:
        if not asset.startswith("/static/"):
            continue
        parsed = urlsplit(asset)
        file_path = STATIC / Path(parsed.path).name
        if not file_path.is_file():
            missing_assets.append(asset)
        if parsed.query != "v=0.0.15":
            stale_assets.append(asset)
    if missing_assets:
        fail(f"Missing static assets: {missing_assets}")
    if stale_assets:
        fail(f"Static assets without 0.0.15 cache key: {stale_assets}")

    required_ids = {
        "scope-select",
        "scope-context-label",
        "technical-brain",
        "chat-form",
        "development-module",
        "attention-module",
        "evolution-module",
        "research-module",
        "communication-module",
        "documents-module",
        "documents-modal",
        "settings-module",
        "placeholder-module",
        "placeholder-readiness",
        "placeholder-available",
        "placeholder-scope",
        "placeholder-next",
    }
    missing_ids = sorted(required_ids - set(parser.ids))
    if missing_ids:
        fail(f"Missing UI contract ids: {missing_ids}")

    dialog = parser.attrs_by_id.get("documents-modal") or {}
    if (
        dialog.get("role") != "dialog"
        or dialog.get("aria-modal") != "true"
        or dialog.get("aria-hidden") != "true"
    ):
        fail("Document modal accessibility contract is incomplete")

    js_modules = [
        "app.js",
        "live_brain.js",
        "growth.js",
        "intelligence.js",
        "proactive_intelligence.js",
        "evolution.js",
        "research.js",
        "communication.js",
        "documents.js",
    ]
    scope_required = {
        "live_brain.js",
        "growth.js",
        "intelligence.js",
        "proactive_intelligence.js",
        "evolution.js",
        "research.js",
        "communication.js",
        "documents.js",
    }
    for name in js_modules:
        text = (STATIC / name).read_text(encoding="utf-8")
        if name in scope_required and "AISHIN_SCOPE" not in text:
            fail(f"{name} bypasses active scope")
        inline_tiny = [
            float(match.group(1))
            for match in re.finditer(
                r'font-size=["\']([0-9.]+)["\']',
                text,
                re.IGNORECASE,
            )
            if float(match.group(1)) < 10.0
        ]
        if inline_tiny:
            fail(
                f"{name} generates unreadable inline SVG font sizes: "
                f"{inline_tiny}"
            )
        if re.search(
            r'JSON\.stringify\(\{\s*scope\s*:\s*["\']personal["\']',
            text,
        ):
            fail(f"{name} hardcodes personal scope in mutation body")

    app_js = (STATIC / "app.js").read_text(encoding="utf-8")
    if "Здесь будет" in app_js or "Здесь будут" in app_js:
        fail(
            "Future module UI must expose readiness, not pretend unfinished "
            "screens are ordinary modules"
        )
    for marker in (
        "BACKEND НЕ ПОДКЛЮЧЁН",
        "КЛИЕНТ НЕ ПОДКЛЮЧЁН",
        "PROJECT SCOPE РАБОТАЕТ",
    ):
        if marker not in app_js:
            fail(f"Future module readiness marker missing: {marker}")
    if "45000" not in app_js:
        fail("Heavy dashboard polling guard is missing")

    documents_js = (STATIC / "documents.js").read_text(
        encoding="utf-8"
    )
    for marker in (
        "trapModalFocus",
        "modalFocusable",
        "modalReturnFocus",
        'setAttribute("aria-hidden","false")',
        'setAttribute("aria-hidden","true")',
    ):
        if marker not in documents_js:
            fail(
                f"Document dialog keyboard/accessibility marker missing: "
                f"{marker}"
            )

    live_js = (STATIC / "live_brain.js").read_text(encoding="utf-8")
    for marker in (
        "new EventSource",
        "/api/assistant/live-brain/stream",
        "brain-wire",
        "renderRealtimePulse",
        "executing",
        "recent",
        "brain-flow-legend",
        "lb-node-inspector",
        "lb-flow-request",
        "lb-flow-concurrency",
        "stateLabel",
        "Research evidence",
        "Фактически выполнено",
        "lb-grounding-score",
        "Grounding ответа",
        "AISHIN 00.00.14",
    ):
        if marker not in live_js:
            fail(f"Live Brain real-time marker missing: {marker}")

    css_files = [
        "style.css",
        "live_brain.css",
        "growth.css",
        "intelligence.css",
        "proactive_intelligence.css",
        "evolution.css",
        "research.css",
        "communication.css",
        "documents.css",
    ]
    tiny_fonts = []
    no_responsive = []
    for name in css_files:
        text = (STATIC / name).read_text(encoding="utf-8")
        values = [
            float(match.group(1))
            for match in re.finditer(
                r"font-size\s*:\s*([0-9.]+)px",
                text,
                re.IGNORECASE,
            )
        ]
        if values and min(values) < 10.0:
            tiny_fonts.append((name, min(values)))
        if "@media" not in text:
            no_responsive.append(name)
    if tiny_fonts:
        fail(f"Unreadable literal font sizes detected: {tiny_fonts}")
    if no_responsive:
        fail(f"CSS modules without responsive rules: {no_responsive}")

    print(
        "UI contract OK: "
        f"{len(parser.ids)} ids, {len(parser.assets)} assets, "
        f"{len(css_files)} responsive stylesheets, "
        "real-time brain + response grounding + knowledge lifecycle + canonical facts + scoped modules verified"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"UI CONTRACT FAILED: {exc}", file=sys.stderr)
        raise
