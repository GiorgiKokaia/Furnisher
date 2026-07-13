"""Small LLM provider wrapper (docs/04): the rest of the codebase talks to this surface only,
so swapping providers later stays cheap. Prototype backend: Gemini via google-genai.

Content items may be: str, Path (image file), or (bytes, mime_type) tuples.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from furnisher.config import Settings

log = logging.getLogger(__name__)

M = TypeVar("M", bound=BaseModel)

_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


class LLMError(RuntimeError):
    pass


def _to_parts(content) -> list:
    from google.genai import types

    if isinstance(content, (str, Path, tuple)):
        content = [content]
    parts = []
    for c in content:
        if isinstance(c, str):
            parts.append(types.Part.from_text(text=c))
        elif isinstance(c, Path):
            mime = _MIME.get(c.suffix.lower())
            if mime is None:
                raise LLMError(f"unsupported image type: {c}")
            parts.append(types.Part.from_bytes(data=c.read_bytes(), mime_type=mime))
        elif isinstance(c, tuple):
            data, mime = c
            parts.append(types.Part.from_bytes(data=data, mime_type=mime))
        else:
            raise LLMError(f"unsupported content item: {type(c)}")
    return parts


class GeminiLLM:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        if not self.settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY is not set (repo-root .env or environment)")
        from google import genai

        self.client = genai.Client(api_key=self.settings.gemini_api_key)

    def complete(
        self,
        content,
        *,
        system: str | None = None,
        tools: list[Callable] | None = None,
    ) -> str:
        """Free-text completion. `tools` are plain Python functions — the SDK runs the
        function-calling loop automatically."""
        from google.genai import types

        config = types.GenerateContentConfig(system_instruction=system, tools=tools or None)
        last = None
        for attempt in range(3):  # flash occasionally emits MALFORMED_FUNCTION_CALL; retry
            resp = self.client.models.generate_content(
                model=self.settings.chat_model, contents=_to_parts(content), config=config
            )
            if resp.text is not None:
                return resp.text
            last = resp
            reason = resp.candidates[0].finish_reason if resp.candidates else "?"
            log.warning("empty completion (finish_reason=%s), attempt %d/3", reason, attempt + 1)
        raise LLMError(f"no text in response after retries: {last}")

    def complete_structured(
        self,
        content,
        schema: type[M],
        *,
        system: str | None = None,
    ) -> M:
        """JSON-schema-enforced completion, parsed into the given Pydantic model."""
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
        )
        resp = self.client.models.generate_content(
            model=self.settings.chat_model, contents=_to_parts(content), config=config
        )
        if isinstance(resp.parsed, schema):
            return resp.parsed
        if resp.text:
            return schema.model_validate_json(resp.text)
        raise LLMError(f"no parseable response: {resp}")

    def generate_image(self, content) -> bytes:
        """Image generation/composition (Nano Banana). Returns PNG/JPEG bytes."""
        resp = self.client.models.generate_content(
            model=self.settings.image_model, contents=_to_parts(content)
        )
        for candidate in resp.candidates or []:
            for part in candidate.content.parts or []:
                if part.inline_data and part.inline_data.data:
                    return part.inline_data.data
        raise LLMError("no image in response")
