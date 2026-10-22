import json
import logging
from typing import Any, Optional, Sequence

from app.core.config import settings

logger = logging.getLogger(__name__)

import importlib

try:
    genai = importlib.import_module("google.genai")
    types = importlib.import_module("google.genai.types")
except Exception:
    genai = None

    class _InlineData:
        def __init__(self, data: bytes, mime_type: str):
            self.data = data
            self.mime_type = mime_type

    class _Part:
        def __init__(self, data: bytes, mime_type: str):
            self.inline_data = _InlineData(data=data, mime_type=mime_type)

        @classmethod
        def from_bytes(cls, data: bytes, mime_type: str):
            return cls(data=data, mime_type=mime_type)

    class _GenerateContentConfig:
        def __init__(
            self,
            temperature: float = 0.0,
            response_mime_type: Optional[str] = None,
            response_schema: Optional[Any] = None,
            system_instruction: Optional[str] = None,
        ):
            self.temperature = temperature
            self.response_mime_type = response_mime_type
            self.response_schema = response_schema
            self.system_instruction = system_instruction

    class _Types:
        Part = _Part
        GenerateContentConfig = _GenerateContentConfig

    types = _Types()


class LLMClient:
    """
    Provider-independent LLM client.

    Currently:
        Gemini 2.5 Flash-Lite

    Later this same interface can be changed to:
        Qwen3-VL
        Ollama
        vLLM
        another OpenAI-compatible provider
    """

    def __init__(self):
        self.client = (
            genai.Client(api_key=settings.LLM_API_KEY)
            if genai is not None
            and settings.LLM_PROVIDER.lower() == "gemini"
            and settings.LLM_API_KEY
            else None
        )
        self.model = settings.LLM_MODEL

    def is_available(self, model: Optional[str] = None) -> bool:
        if self.client is None:
            return False

        try:
            self.client.models.get(model=model or self.model)
        except Exception as exc:
            logger.warning("LLM provider is unavailable: %s", exc)
            return False
        return True

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        if self.client is None:
            raise RuntimeError("LLM provider is not configured.")

        config = types.GenerateContentConfig(
            temperature=settings.LLM_TEMPERATURE,
        )

        if system_instruction:
            config.system_instruction = system_instruction

        response = self.client.models.generate_content(
            model=model or self.model,
            contents=prompt,
            config=config,
        )

        if not response.text:
            raise RuntimeError("Gemini returned an empty response.")

        return response.text

    def generate_json(
        self,
        prompt: str,
        response_schema: Optional[dict[str, Any]] = None,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        image_inputs: Optional[Sequence[tuple[bytes, str]]] = None,
    ) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("LLM provider is not configured.")

        config = types.GenerateContentConfig(
            temperature=settings.LLM_TEMPERATURE,
            response_mime_type="application/json",
        )

        if response_schema:
            config.response_schema = response_schema

        if system_instruction:
            config.system_instruction = system_instruction

        contents: str | list[Any] = prompt
        if image_inputs:
            contents = [
                prompt,
                *[
                    types.Part.from_bytes(
                        data=image_data,
                        mime_type=mime_type,
                    )
                    for image_data, mime_type in image_inputs
                ],
            ]

        response = self.client.models.generate_content(
            model=model or self.model,
            contents=contents,
            config=config,
        )

        if not response.text:
            raise RuntimeError("Gemini returned an empty JSON response.")

        try:
            return json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Gemini returned invalid JSON:\n{response.text}"
            ) from exc


llm_client = LLMClient()
ollama_client = llm_client


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