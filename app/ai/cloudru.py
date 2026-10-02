from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .provider import AIReply


class CloudRuProvider:
    """Cloud.ru Evolution Foundation Models provider.

    Uses the OpenAI-compatible endpoints:
    GET  /v1/models
    POST /v1/chat/completions
    """

    name = "cloud.ru"

    def __init__(self) -> None:
        self.base_url = os.getenv(
            "AISHIN_CLOUDRU_URL",
            "https://foundation-models.api.cloud.ru/v1",
        ).rstrip("/")
        self.api_key = os.getenv("AISHIN_CLOUDRU_API_KEY", "").strip()
        self.model = os.getenv(
            "AISHIN_CLOUDRU_MODEL",
            "ai-sage/GigaChat3-10B-A1.8B",
        ).strip()
        self.timeout = float(os.getenv("AISHIN_CLOUDRU_TIMEOUT", "120"))

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, path: str, payload: dict | None = None) -> dict:
        if not self.api_key:
            raise RuntimeError("AISHIN_CLOUDRU_API_KEY не задан")

        body = None
        method = "GET"
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            method = "POST"

        request = Request(
            self.base_url + path,
            data=body,
            headers=self._headers(),
            method=method,
        )
        with urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def health(self) -> dict:
        if not self.api_key:
            return {
                "available": False,
                "provider": self.name,
                "model": self.model,
                "configured": False,
                "error": "API-ключ Cloud.ru не настроен",
            }

        try:
            data = self._request("/models")
            models = [
                item.get("id", "")
                for item in data.get("data", [])
                if isinstance(item, dict)
            ]
            return {
                "available": True,
                "provider": self.name,
                "model": self.model,
                "configured": True,
                "model_available": self.model in models,
                "models_count": len(models),
            }
        except Exception as exc:
            return {
                "available": False,
                "provider": self.name,
                "model": self.model,
                "configured": True,
                "error": str(exc),
            }

    def chat(self, *, system: str, messages: list[dict[str, str]]) -> AIReply:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": 0.45,
        }

        try:
            data = self._request("/chat/completions", payload)
            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError("Cloud.ru вернул ответ без choices")

            message = choices[0].get("message") or {}
            text = (message.get("content") or "").strip()
            if not text:
                raise RuntimeError("Cloud.ru вернул пустой ответ")

            return AIReply(
                text=text,
                provider=self.name,
                model=self.model,
                available=True,
            )
        except (HTTPError, URLError, TimeoutError, OSError, RuntimeError) as exc:
            return AIReply(
                text=str(exc),
                provider=self.name,
                model=self.model,
                available=False,
            )
