import json
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings


class OllamaClient:
    """Direct, robust client for Ollama LLM execution supporting format: 'json'."""

    def __init__(self, base_url: Optional[str] = None, default_model: Optional[str] = None):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.default_model = default_model or settings.LLM_MODEL

    def is_available(self) -> bool:
        """Check if Ollama service is reachable."""
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """List currently downloaded models in Ollama."""
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    models = res.json().get("models", [])
                    return [m.get("name") for m in models if m.get("name")]
        except Exception:
            pass
        return []

    def generate_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: float = 120.0,
    ) -> Dict[str, Any]:
        """
        Invoke Ollama with strict JSON output formatting.
        Returns the parsed JSON dictionary.
        """
        target_model = model or self.default_model
        payload = {
            "model": target_model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.0,
            },
        }
        if system:
            payload["system"] = system

        try:
            with httpx.Client(timeout=timeout_seconds) as client:
                res = client.post(f"{self.base_url}/api/generate", json=payload)
                if res.status_code != 200:
                    raise RuntimeError(f"Ollama returned HTTP {res.status_code}: {res.text}")
                data = res.json()
                raw_response = data.get("response", "{}")
                return json.loads(raw_response)
        except httpx.ConnectError:
            raise ConnectionError(
                f"Cannot connect to Ollama at '{self.base_url}'. Ensure Ollama is running and accessible."
            )
        except json.JSONDecodeError as jde:
            raise ValueError(f"Failed to decode Ollama JSON response: {str(jde)}")


ollama_client = OllamaClient()
llm_client = ollama_client


def get_llm():
    """Optional LangChain adapter if langchain_ollama is installed."""
    try:
        import importlib
        langchain_ollama = importlib.import_module("langchain_ollama")
        return langchain_ollama.ChatOllama(
            model=settings.LLM_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=0,
        )
    except Exception:
        return None