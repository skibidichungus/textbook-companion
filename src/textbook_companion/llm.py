"""LLM client protocol and Claude implementation.

The rest of the project talks to the LLM only through `LLMClient`. Only this
module imports `anthropic` — swap in a local-model implementation later
without touching the session loop.

Structured output uses *forced tool use*: the Pydantic schema becomes a tool's
`input_schema`, and `tool_choice` forces the model to call it. We parse the
tool call's `input` back through the schema. Anthropic has no JSON-mode flag
like OpenAI; this is the canonical structured-output pattern.

Prompt caching sets `cache_control={"type": "ephemeral"}` on the last system
block. For Opus 4.7 the minimum cacheable prefix is 4096 tokens — below that,
caching silently no-ops, so we log a warning.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Protocol, TypeVar, runtime_checkable

import anthropic
from pydantic import BaseModel


logger = logging.getLogger(__name__)


DEFAULT_MODEL = "claude-opus-4-7"

# Opus 4.7's minimum cacheable prefix (tokens). Anything shorter cached
# silently no-ops — cache_creation_input_tokens will be 0.
MIN_CACHE_TOKENS_OPUS_4_7 = 4096

DEFAULT_MAX_TOKENS = 16000


T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class LLMClient(Protocol):
    """The one abstraction this project needs from an LLM backend."""

    def chat(
        self,
        system: str,
        messages: list[dict[str, Any]],
        cache_system: bool = True,
    ) -> str: ...

    def structured(
        self,
        system: str,
        user: str,
        schema: type[T],
    ) -> T: ...


class StructuredOutputError(RuntimeError):
    """Raised when the model did not emit the forced tool call we asked for."""


class ClaudeClient:
    """Concrete `LLMClient` backed by the Anthropic SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY")
        self._client = anthropic.Anthropic(api_key=key)
        self.model = model
        self.max_tokens = max_tokens

    def chat(
        self,
        system: str,
        messages: list[dict[str, Any]],
        cache_system: bool = True,
    ) -> str:
        system_blocks = self._build_system_blocks(system, cache_system)
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_blocks,
            messages=messages,
        )
        return "".join(
            block.text for block in response.content if block.type == "text"
        )

    def structured(
        self,
        system: str,
        user: str,
        schema: type[T],
    ) -> T:
        tool_name = _tool_name_for(schema)
        tool = {
            "name": tool_name,
            "description": f"Record a validated {schema.__name__} object.",
            "input_schema": schema.model_json_schema(),
        }
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": user}],
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return schema.model_validate(block.input)
        raise StructuredOutputError(
            f"model did not emit the forced tool call '{tool_name}'"
        )

    def _build_system_blocks(
        self, system: str, cache_system: bool
    ) -> list[dict[str, Any]]:
        block: dict[str, Any] = {"type": "text", "text": system}
        if cache_system:
            if _estimate_tokens(system) < MIN_CACHE_TOKENS_OPUS_4_7:
                logger.warning(
                    "system prompt is below the %d-token minimum for Opus 4.7 "
                    "prompt caching; cache_control will be accepted but will "
                    "silently no-op",
                    MIN_CACHE_TOKENS_OPUS_4_7,
                )
            block["cache_control"] = {"type": "ephemeral"}
        return [block]


def _tool_name_for(schema: type[BaseModel]) -> str:
    """A stable, Anthropic-safe tool name derived from the schema class name."""
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in schema.__name__)
    return f"emit_{safe.lower()}"


def _estimate_tokens(text: str) -> int:
    """Rough ~4 chars/token estimate — good enough for a threshold warning."""
    return len(text) // 4
