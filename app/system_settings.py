from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values, set_key

from .ai import AIManager


DEFAULTS = {
    "AISHIN_AI_PROVIDER": "cloudru",
    "AISHIN_CLOUDRU_URL": "https://foundation-models.api.cloud.ru/v1",
    "AISHIN_CLOUDRU_MODEL": "ai-sage/GigaChat3-10B-A1.8B",
    "AISHIN_CLOUDRU_TIMEOUT": "120",
    "AISHIN_CLOUDRU_EMBEDDING_MODEL": "Qwen/Qwen3-Embedding-0.6B",
    "AISHIN_CLOUDRU_EMBEDDING_DIMENSIONS": "1024",
    "AISHIN_CLOUDRU_MAX_RETRIES": "2",
    "AISHIN_CLOUDRU_BACKOFF_BASE": "0.5",
    "AISHIN_CLOUDRU_MAX_BACKOFF": "4",
    "AISHIN_CLOUDRU_HEALTH_TTL": "30",
}


class CloudSettingsService:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.env_path = root / ".env"

    def public_status(self) -> dict:
        values = self._merged_values()
        configured = bool(
            str(values.get("AISHIN_CLOUDRU_API_KEY") or "").strip()
        )
        return {
            "provider": str(
                values.get("AISHIN_AI_PROVIDER")
                or DEFAULTS["AISHIN_AI_PROVIDER"]
            ),
            "configured": configured,
            "base_url": str(
                values.get("AISHIN_CLOUDRU_URL")
                or DEFAULTS["AISHIN_CLOUDRU_URL"]
            ),
            "model": str(
                values.get("AISHIN_CLOUDRU_MODEL")
                or DEFAULTS["AISHIN_CLOUDRU_MODEL"]
            ),
            "embedding_model": str(
                values.get("AISHIN_CLOUDRU_EMBEDDING_MODEL")
                or DEFAULTS["AISHIN_CLOUDRU_EMBEDDING_MODEL"]
            ),
            "env_exists": self.env_path.is_file(),
        }

    def save_key(self, api_key: str) -> dict:
        key = api_key.strip()
        if len(key) < 12:
            raise ValueError("API-ключ выглядит слишком коротким")

        self.env_path.touch(exist_ok=True)
        for name, value in DEFAULTS.items():
            set_key(
                str(self.env_path),
                name,
                value,
                quote_mode="always",
            )
            os.environ[name] = value

        set_key(
            str(self.env_path),
            "AISHIN_CLOUDRU_API_KEY",
            key,
            quote_mode="never",
        )
        os.environ["AISHIN_CLOUDRU_API_KEY"] = key
        try:
            self.env_path.chmod(0o600)
        except OSError:
            pass
        return self.public_status()

    def test(self) -> dict:
        manager = AIManager()
        if manager.mode not in {"cloudru", "cloud.ru"}:
            return {
                "available": False,
                "configured": False,
                "provider": manager.mode,
                "error": "Cloud.ru не выбран как AI-провайдер",
            }
        return manager.cloudru.health(force=True)

    def _merged_values(self) -> dict:
        values: dict = {}
        if self.env_path.is_file():
            values.update(dotenv_values(self.env_path))
        for name in (*DEFAULTS.keys(), "AISHIN_CLOUDRU_API_KEY"):
            if name in os.environ:
                values[name] = os.environ[name]
        return values
