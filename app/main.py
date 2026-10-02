from __future__ import annotations

import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

from .db import init_db, list_modules, record_update
from .personality import personality

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = Path(__file__).resolve().parent

templates = Environment(
    loader=FileSystemLoader(APP_DIR / "templates"),
    autoescape=select_autoescape(["html", "xml"]),
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Aishin Kitsune", version="0.0.1", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


class ChatMessage(BaseModel):
    message: str


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    template = templates.get_template("index.html")
    return template.render(
        title="Aishin Kitsune",
        modules=list_modules(),
        profile=personality.public_summary(),
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "name": personality.name, "version": "0.0.1"}


@app.get("/api/modules")
def modules() -> list[dict]:
    return list_modules()


@app.get("/api/assistant/profile")
def assistant_profile() -> dict:
    return personality.public_summary()


@app.post("/api/assistant/message")
def assistant_message(payload: ChatMessage) -> dict:
    text = payload.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Сообщение пустое")

    lowered = text.lower()
    if any(word in lowered for word in ("привет", "здравств", "айшин", "айши")):
        reply = "С возвращением, Господин. Я рядом."
    elif any(word in lowered for word in ("кто ты", "твоя душа", "характер")):
        reply = (
            "Я Айшин — Ваша личная помощница. Моя основа уже отделена от "
            "конкретной AI-модели: характер, принципы и память будут сохраняться "
            "при смене модели."
        )
    else:
        reply = (
            "Я получила сообщение, Господин. Сейчас работает моё базовое ядро. "
            "Следующим слоем мы подключим настоящий AI-движок и долговременную память."
        )

    return {
        "reply": reply,
        "phase": "foundation",
        "llm_connected": False,
    }


def _local_only(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="Обновление разрешено только локально")


@app.post("/api/system/update")
def system_update(request: Request) -> dict:
    _local_only(request)
    try:
        fetch = subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        pull = subprocess.run(
            ["git", "pull", "--ff-only", "origin", "main"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        details = (fetch.stdout + "\n" + pull.stdout).strip() or "Обновление проверено"
        record_update("success", details)
        return {"status": "success", "details": details}
    except Exception as exc:
        details = str(exc)
        record_update("error", details)
        raise HTTPException(status_code=500, detail=details)
