import json
import logging
from typing import Any, Optional, Sequence

from openai import OpenAI

from app.core.config import settings


logger = logging.getLogger(__name__)


class LLMClient:
    """
    Provider-independent LLM client.

    Supports OpenAI-compatible APIs such as:
    - Qwen3-VL-4B-Instruct through a hosted provider
    - Qwen3-VL through vLLM
    - Other OpenAI-compatible inference servers
    """

    def __init__(self):
        self.provider = settings.LLM_PROVIDER.lower()
        self.model = settings.LLM_MODEL

        self.client = None

        if self.provider == "qwen":
            if not settings.LLM_API_KEY:
                logger.warning("Qwen API key is not configured.")
            elif not settings.LLM_BASE_URL:
                logger.warning("Qwen API base URL is not configured.")
            else:
                self.client = OpenAI(
                    api_key=settings.LLM_API_KEY,
                    base_url=settings.LLM_BASE_URL,
                    timeout=settings.LLM_TIMEOUT_SECONDS,
                )

    def is_available(self, model: Optional[str] = None) -> bool:
        if self.client is None:
            return False

        try:
            response = self.client.models.list()

            # If the provider successfully responds,
            # the API is reachable.
            return response is not None

        except Exception as exc:
            logger.warning(
                "LLM provider is unavailable: %s",
                exc,
            )
            return False

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:

        if self.client is None:
            raise RuntimeError(
                "Qwen API is not configured."
            )

        messages = []

        if system_instruction:
            messages.append(
                {
                    "role": "system",
                    "content": system_instruction,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        response = self.client.chat.completions.create(
            model=model or self.model,
            messages=messages,
            temperature=settings.LLM_TEMPERATURE,
        )

        if not response.choices:
            raise RuntimeError(
                "Qwen returned an empty response."
            )

        content = response.choices[0].message.content

        if not content:
            raise RuntimeError(
                "Qwen returned an empty response."
            )

        return content

    def generate_json(
        self,
        prompt: str,
        response_schema: Optional[dict[str, Any]] = None,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        image_inputs: Optional[
            Sequence[tuple[bytes, str]]
        ] = None,
    ) -> dict[str, Any]:

        if self.client is None:
            raise RuntimeError(
                "Qwen API is not configured."
            )

        messages = []

        if system_instruction:
            messages.append(
                {
                    "role": "system",
                    "content": system_instruction,
                }
            )

        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": prompt,
            }
        ]

        if image_inputs:
            import base64

            for image_data, mime_type in image_inputs:
                encoded_image = base64.b64encode(
                    image_data
                ).decode("utf-8")

                content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": (
                                f"data:{mime_type};base64,"
                                f"{encoded_image}"
                            )
                        },
                    }
                )

        messages.append(
            {
                "role": "user",
                "content": content,
            }
        )

        request_kwargs = {
            "model": model or self.model,
            "messages": messages,
            "temperature": settings.LLM_TEMPERATURE,
        }

        # Ask the model to return JSON.
        request_kwargs["response_format"] = {
            "type": "json_object"
        }

        response = self.client.chat.completions.create(
            **request_kwargs
        )

        if not response.choices:
            raise RuntimeError(
                "Qwen returned an empty response."
            )

        content = response.choices[0].message.content

        if not content:
            raise RuntimeError(
                "Qwen returned an empty JSON response."
            )

        try:
            return json.loads(content)

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Qwen returned invalid JSON:\n"
                f"{content}"
            ) from exc


llm_client = LLMClient()