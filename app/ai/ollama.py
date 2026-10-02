from __future__ import annotations

import json
import os
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from .provider import AIReply

class OllamaProvider:
    name = 'ollama'

    def __init__(self) -> None:
        self.base_url = os.getenv('AISHIN_OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
        self.model = os.getenv('AISHIN_OLLAMA_MODEL', 'qwen3.5:4b')
        self.timeout = float(os.getenv('AISHIN_OLLAMA_TIMEOUT', '120'))

    def _request(self, path: str, payload: dict | None = None) -> dict:
        body = None if payload is None else json.dumps(payload).encode('utf-8')
        req = Request(self.base_url + path, data=body, headers={'Content-Type':'application/json'})
        with urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode('utf-8'))

    def health(self) -> dict:
        try:
            data = self._request('/api/tags')
            models = [m.get('name','') for m in data.get('models', [])]
            return {'available': True, 'provider': self.name, 'model': self.model, 'installed_models': models, 'model_installed': self.model in models}
        except Exception as exc:
            return {'available': False, 'provider': self.name, 'model': self.model, 'error': str(exc)}

    def chat(self, *, system: str, messages: list[dict[str, str]]) -> AIReply:
        payload = {
            'model': self.model,
            'stream': False,
            'messages': [{'role':'system','content':system}, *messages],
            'options': {'temperature': 0.45}
        }
        try:
            data = self._request('/api/chat', payload)
            text = (data.get('message') or {}).get('content','').strip()
            if not text:
                raise RuntimeError('Ollama вернула пустой ответ')
            return AIReply(text=text, provider=self.name, model=self.model, available=True)
        except (URLError, HTTPError, TimeoutError, OSError, RuntimeError) as exc:
            return AIReply(text=str(exc), provider=self.name, model=self.model, available=False)
