import json
from typing import Any, Optional

from google import genai
from google.genai import types

from app.core.config import settings


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
        if settings.LLM_PROVIDER.lower() != "gemini":
            raise ValueError(
                f"Unsupported LLM provider: {settings.LLM_PROVIDER}"
            )

        if not settings.LLM_API_KEY:
            raise ValueError(
                "LLM_API_KEY is missing. "
                "Add your Gemini API key to the .env file."
            )

        self.client = genai.Client(
            api_key=settings.LLM_API_KEY
        )

        self.model = settings.LLM_MODEL

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
    ) -> str:

        config = types.GenerateContentConfig(
            temperature=settings.LLM_TEMPERATURE,
        )

        if system_instruction:
            config.system_instruction = system_instruction

        response = self.client.models.generate_content(
            model=self.model,
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
    ) -> dict[str, Any]:

        config = types.GenerateContentConfig(
            temperature=settings.LLM_TEMPERATURE,
            response_mime_type="application/json",
        )

        if response_schema:
            config.response_schema = response_schema

        if system_instruction:
            config.system_instruction = system_instruction

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
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