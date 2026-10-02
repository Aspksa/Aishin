from __future__ import annotations

import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path


PROTECTED_TOP_LEVEL = {
    ".env",
    ".git",
    ".venv",
    ".aishin_backups",
    "data",
    "logs",
}


class ProjectUpdater:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def update(self) -> dict:
        if self._is_git_checkout():
            try:
                return self._git_update()
            except Exception as exc:
                # A broken/missing remote should not make ZIP installs unusable.
                return self._zip_update(fallback_reason=str(exc))
        return self._zip_update()

    def mode(self) -> str:
        return "git" if self._is_git_checkout() else "zip"

    def _is_git_checkout(self) -> bool:
        return (self.root / ".git").exists()

    def _git_update(self) -> dict:
        fetch = subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=45,
            check=True,
        )
        pull = subprocess.run(
            ["git", "pull", "--ff-only", "origin", "main"],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=45,
            check=True,
        )
        details = (fetch.stdout + "\n" + pull.stdout).strip()
        return {
            "status": "success",
            "mode": "git",
            "restart_required": True,
            "details": details or "GitHub update checked.",
        }

    def _zip_update(self, fallback_reason: str = "") -> dict:
        url = "https://github.com/Aspksa/Aishin/archive/refs/heads/main.zip"
        with tempfile.TemporaryDirectory(prefix="aishin-update-") as tmp:
            temp_dir = Path(tmp)
            archive = temp_dir / "main.zip"
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Aishin-Updater/0.0.3"},
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                archive.write_bytes(response.read())

            with zipfile.ZipFile(archive) as zf:
                bad = zf.testzip()
                if bad:
                    raise RuntimeError(
                        f"GitHub ZIP integrity check failed: {bad}"
                    )
                zf.extractall(temp_dir / "extract")

            extracted = temp_dir / "extract"
            roots = [p for p in extracted.iterdir() if p.is_dir()]
            if len(roots) != 1:
                raise RuntimeError("Unexpected GitHub archive layout")
            source = roots[0]

            copied = 0
            for item in source.iterdir():
                if item.name in PROTECTED_TOP_LEVEL:
                    continue
                target = self.root / item.name
                if item.is_dir():
                    shutil.copytree(
                        item,
                        target,
                        dirs_exist_ok=True,
                        copy_function=shutil.copy2,
                    )
                else:
                    shutil.copy2(item, target)
                copied += 1

        detail = (
            f"ZIP update installed safely; {copied} top-level items refreshed."
        )
        if fallback_reason:
            detail += " Git mode fallback was used."

        return {
            "status": "success",
            "mode": "zip",
            "restart_required": True,
            "preserved": sorted(PROTECTED_TOP_LEVEL),
            "details": detail,
        }
