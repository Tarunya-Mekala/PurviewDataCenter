from typing import Any, Dict, List, Optional

from app.ai.llm import llm_client
from app.ai.prompts.mapping_prompt import (
    MAPPING_SYSTEM_PROMPT,
    build_mapping_prompt,
)


class MappingService:
    """
    Semantic column mapping service.

    The LLM determines the meaning of arbitrary source
    column names and maps them to canonical fields.
    """

    MIN_CONFIDENCE = 0.65

    @staticmethod
    def semantic_map_columns(
        category: str,
        source_columns: List[str],
        sample_rows: List[Dict[str, Any]],
        model: Optional[str] = None,
    ) -> Dict[str, str]:

        if not source_columns:
            return {}

        prompt = build_mapping_prompt(
            category=category,
            source_columns=source_columns,
            sample_rows=sample_rows,
        )

        response = llm_client.generate_json(
            prompt=prompt,
            system_instruction=MAPPING_SYSTEM_PROMPT,
        )

        mappings = response.get(
            "mappings",
            [],
        )

        if not isinstance(
            mappings,
            list,
        ):
            return {}

        result: Dict[str, str] = {}

        for item in mappings:

            if not isinstance(
                item,
                dict,
            ):
                continue

            source = str(
                item.get(
                    "source_column",
                    "",
                )
                or ""
            ).strip()

            canonical = str(
                item.get(
                    "canonical_field",
                    "",
                )
                or ""
            ).strip()

            try:

                confidence = float(
                    item.get(
                        "confidence",
                        0,
                    )
                )

            except (
                TypeError,
                ValueError,
            ):

                confidence = 0.0

            if (
                source
                and canonical
                and confidence
                >= MappingService.MIN_CONFIDENCE
            ):

                result[source] = canonical

        return result


mapping_service = MappingService()