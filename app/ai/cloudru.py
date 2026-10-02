from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .provider import AIReply, EmbeddingReply


@dataclass
class RequestFailure(Exception):
    message: str
    code: str
    attempts: int
    latency_ms: int
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


class CloudRuProvider:
    """Cloud.ru Evolution Foundation Models provider with bounded resilience."""

    name = "cloud.ru"
    RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}

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
        self.embedding_model = os.getenv(
            "AISHIN_CLOUDRU_EMBEDDING_MODEL",
            "Qwen/Qwen3-Embedding-0.6B",
        ).strip()
        self.embedding_dimensions = int(
            os.getenv("AISHIN_CLOUDRU_EMBEDDING_DIMENSIONS", "1024")
        )

        self.timeout = self._bounded_float(
            os.getenv("AISHIN_CLOUDRU_TIMEOUT", "120"),
            default=120.0,
            minimum=5.0,
            maximum=300.0,
        )
        self.max_retries = self._bounded_int(
            os.getenv("AISHIN_CLOUDRU_MAX_RETRIES", "2"),
            default=2,
            minimum=0,
            maximum=4,
        )
        self.backoff_base = self._bounded_float(
            os.getenv("AISHIN_CLOUDRU_BACKOFF_BASE", "0.5"),
            default=0.5,
            minimum=0.1,
            maximum=5.0,
        )
        self.max_backoff = self._bounded_float(
            os.getenv("AISHIN_CLOUDRU_MAX_BACKOFF", "4"),
            default=4.0,
            minimum=0.2,
            maximum=20.0,
        )
        self.health_ttl = self._bounded_float(
            os.getenv("AISHIN_CLOUDRU_HEALTH_TTL", "30"),
            default=30.0,
            minimum=5.0,
            maximum=300.0,
        )

        self._health_lock = threading.Lock()
        self._health_cache: dict | None = None
        self._health_cached_at = 0.0

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(
        self,
        path: str,
        payload: dict | None = None,
        *,
        max_retries: int | None = None,
    ) -> tuple[dict, dict]:
        if not self.api_key:
            raise RequestFailure(
                "API-ключ Cloud.ru не настроен",
                "not_configured",
                0,
                0,
                False,
            )

        body = None
        method = "GET"
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            method = "POST"

        retries = self.max_retries if max_retries is None else max_retries
        retries = max(0, min(int(retries), self.max_retries))
        max_attempts = retries + 1
        started = time.monotonic()
        last_failure: RequestFailure | None = None

        for attempt in range(1, max_attempts + 1):
            request = Request(
                self.base_url + path,
                data=body,
                headers=self._headers(),
                method=method,
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                    data = json.loads(raw)
                    latency_ms = int((time.monotonic() - started) * 1000)
                    return data, {
                        "attempts": attempt,
                        "latency_ms": latency_ms,
                        "retries": attempt - 1,
                        "path": path,
                    }
            except HTTPError as exc:
                retryable = int(exc.code) in self.RETRYABLE_HTTP
                failure = RequestFailure(
                    message=self._safe_http_error(exc),
                    code=f"http_{int(exc.code)}",
                    attempts=attempt,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    retryable=retryable,
                )
                last_failure = failure
                if not retryable or attempt >= max_attempts:
                    raise failure
                self._sleep_before_retry(
                    attempt,
                    retry_after=self._retry_after_seconds(exc),
                )
            except (URLError, TimeoutError, OSError) as exc:
                failure = RequestFailure(
                    message=self._safe_network_error(exc),
                    code="network_or_timeout",
                    attempts=attempt,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    retryable=True,
                )
                last_failure = failure
                if attempt >= max_attempts:
                    raise failure
                self._sleep_before_retry(attempt)
            except json.JSONDecodeError:
                raise RequestFailure(
                    "Cloud.ru вернул некорректный JSON",
                    "invalid_json",
                    attempt,
                    int((time.monotonic() - started) * 1000),
                    False,
                )

        if last_failure is not None:
            raise last_failure

        raise RequestFailure(
            "Неизвестная ошибка Cloud.ru",
            "unknown_error",
            0,
            int((time.monotonic() - started) * 1000),
            False,
        )

    def health(self, *, force: bool = False) -> dict:
        now = time.monotonic()

        with self._health_lock:
            if (
                not force
                and self._health_cache is not None
                and now - self._health_cached_at < self.health_ttl
            ):
                cached = dict(self._health_cache)
                cached["cached"] = True
                cached["cache_age_ms"] = int(
                    (now - self._health_cached_at) * 1000
                )
                return cached

        if not self.api_key:
            result = {
                "available": False,
                "provider": self.name,
                "model": self.model,
                "configured": False,
                "error": "API-ключ Cloud.ru не настроен",
                "error_code": "not_configured",
                "cached": False,
                "health_ttl_seconds": self.health_ttl,
            }
            self._store_health(result)
            return result

        try:
            data, meta = self._request("/models", max_retries=1)
            models = [
                item.get("id", "")
                for item in data.get("data", [])
                if isinstance(item, dict)
            ]
            result = {
                "available": True,
                "provider": self.name,
                "model": self.model,
                "configured": True,
                "model_available": self.model in models,
                "models_count": len(models),
                "cached": False,
                "health_ttl_seconds": self.health_ttl,
                "attempts": meta["attempts"],
                "latency_ms": meta["latency_ms"],
            }
        except RequestFailure as exc:
            result = {
                "available": False,
                "provider": self.name,
                "model": self.model,
                "configured": True,
                "error": exc.message,
                "error_code": exc.code,
                "cached": False,
                "health_ttl_seconds": self.health_ttl,
                "attempts": exc.attempts,
                "latency_ms": exc.latency_ms,
            }

        self._store_health(result)
        return result

    def chat(self, *, system: str, messages: list[dict[str, str]]) -> AIReply:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": 0.45,
        }

        try:
            data, meta = self._request("/chat/completions", payload)
            choices = data.get("choices") or []
            if not choices:
                raise RequestFailure(
                    "Cloud.ru вернул ответ без choices",
                    "empty_choices",
                    meta["attempts"],
                    meta["latency_ms"],
                    False,
                )

            message = choices[0].get("message") or {}
            text = (message.get("content") or "").strip()
            if not text:
                raise RequestFailure(
                    "Cloud.ru вернул пустой ответ",
                    "empty_content",
                    meta["attempts"],
                    meta["latency_ms"],
                    False,
                )

            return AIReply(
                text=text,
                provider=self.name,
                model=self.model,
                available=True,
                attempts=meta["attempts"],
                latency_ms=meta["latency_ms"],
                metadata={
                    "retries": meta["retries"],
                    "timeout_seconds": self.timeout,
                },
            )
        except RequestFailure as exc:
            return AIReply(
                text="",
                provider=self.name,
                model=self.model,
                available=False,
                error=exc.message,
                error_code=exc.code,
                attempts=exc.attempts,
                latency_ms=exc.latency_ms,
                metadata={
                    "retryable": exc.retryable,
                    "timeout_seconds": self.timeout,
                },
            )

    def embed(self, texts: list[str]) -> EmbeddingReply:
        clean = [text.strip() for text in texts if text and text.strip()]
        if not clean:
            return EmbeddingReply(
                vectors=[],
                provider=self.name,
                model=self.embedding_model,
                dimensions=self.embedding_dimensions,
                available=True,
                attempts=0,
                latency_ms=0,
            )

        payload = {
            "model": self.embedding_model,
            "input": clean,
        }

        try:
            data, meta = self._request("/embeddings", payload)
            rows = data.get("data") or []
            rows = sorted(
                [row for row in rows if isinstance(row, dict)],
                key=lambda row: int(row.get("index", 0)),
            )
            vectors = [row.get("embedding") for row in rows]
            if len(vectors) != len(clean) or not all(
                isinstance(vector, list) and vector for vector in vectors
            ):
                raise RequestFailure(
                    "Cloud.ru вернул некорректный embedding-ответ",
                    "invalid_embedding_response",
                    meta["attempts"],
                    meta["latency_ms"],
                    False,
                )

            dimensions = len(vectors[0])
            if any(len(vector) != dimensions for vector in vectors):
                raise RequestFailure(
                    "Размерности embedding-векторов не совпадают",
                    "embedding_dimension_mismatch",
                    meta["attempts"],
                    meta["latency_ms"],
                    False,
                )

            return EmbeddingReply(
                vectors=vectors,
                provider=self.name,
                model=self.embedding_model,
                dimensions=dimensions,
                available=True,
                attempts=meta["attempts"],
                latency_ms=meta["latency_ms"],
                metadata={
                    "retries": meta["retries"],
                    "timeout_seconds": self.timeout,
                },
            )
        except RequestFailure as exc:
            return EmbeddingReply(
                vectors=[],
                provider=self.name,
                model=self.embedding_model,
                dimensions=self.embedding_dimensions,
                available=False,
                error=exc.message,
                error_code=exc.code,
                attempts=exc.attempts,
                latency_ms=exc.latency_ms,
                metadata={
                    "retryable": exc.retryable,
                    "timeout_seconds": self.timeout,
                },
            )

    def diagnostics(self) -> dict:
        return {
            "provider": self.name,
            "timeout_seconds": self.timeout,
            "max_retries": self.max_retries,
            "backoff_base_seconds": self.backoff_base,
            "max_backoff_seconds": self.max_backoff,
            "health_ttl_seconds": self.health_ttl,
            "health_cache_present": self._health_cache is not None,
        }

    def _sleep_before_retry(
        self,
        attempt: int,
        *,
        retry_after: float | None = None,
    ) -> None:
        if retry_after is not None:
            delay = min(max(0.0, retry_after), self.max_backoff)
        else:
            delay = min(
                self.max_backoff,
                self.backoff_base * (2 ** max(0, attempt - 1)),
            )
        time.sleep(delay)

    def _store_health(self, result: dict) -> None:
        with self._health_lock:
            self._health_cache = dict(result)
            self._health_cached_at = time.monotonic()

    @staticmethod
    def _safe_http_error(exc: HTTPError) -> str:
        reason = str(getattr(exc, "reason", "") or "").strip()
        if reason:
            return f"Cloud.ru HTTP {int(exc.code)}: {reason[:160]}"
        return f"Cloud.ru HTTP {int(exc.code)}"

    @staticmethod
    def _safe_network_error(exc: Exception) -> str:
        if isinstance(exc, TimeoutError):
            return "Cloud.ru: превышен timeout"
        if isinstance(exc, URLError):
            reason = str(getattr(exc, "reason", "") or "").strip()
            if reason:
                return f"Cloud.ru: временная сетевая ошибка ({reason[:120]})"
        return "Cloud.ru: временная сетевая ошибка"

    @staticmethod
    def _retry_after_seconds(exc: HTTPError) -> float | None:
        value = exc.headers.get("Retry-After") if exc.headers else None
        if not value:
            return None

        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            pass

        try:
            target = parsedate_to_datetime(value)
            now = parsedate_to_datetime(
                time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())
            )
            return max(0.0, (target - now).total_seconds())
        except Exception:
            return None

    @staticmethod
    def _bounded_int(
        raw: str,
        *,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    @staticmethod
    def _bounded_float(
        raw: str,
        *,
        default: float,
        minimum: float,
        maximum: float,
    ) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))
