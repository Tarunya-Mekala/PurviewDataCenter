import json
import logging
from typing import Any, Optional, Sequence

from google import genai
from google.genai import types

from app.core.config import settings


logger = logging.getLogger(__name__)


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
            if settings.LLM_PROVIDER.lower() == "gemini"
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
            raise RuntimeError(
                "Gemini returned an empty JSON response."
            )

        try:
            return json.loads(response.text)

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Gemini returned invalid JSON:\n{response.text}"
            ) from exc


llm_client = LLMClient()