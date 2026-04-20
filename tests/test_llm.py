"""LLM client tests.

Mock-based tests cover cache_control placement, forced tool-use wire shape,
structured-output parsing, and the minimum-tokens warning.

The @pytest.mark.live test hits the real API — it's auto-skipped by the
default pytest config (`addopts = -m "not live"`). Run with `pytest -m live`
when you want to verify end-to-end against Anthropic.
"""

from __future__ import annotations

import logging
import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from textbook_companion import llm
from textbook_companion.llm import (
    DEFAULT_MODEL,
    MIN_CACHE_TOKENS_OPUS_4_7,
    ClaudeClient,
    LLMClient,
    StructuredOutputError,
    _tool_name_for,
)


def _block(**kwargs: Any) -> SimpleNamespace:
    """Lightweight stand-in for an Anthropic content block."""
    return SimpleNamespace(**kwargs)


def _mock_claude_client(response_content: list[SimpleNamespace]) -> tuple[ClaudeClient, MagicMock]:
    """Build a ClaudeClient whose SDK `messages.create` is mocked."""
    with patch("textbook_companion.llm.anthropic") as mock_anthropic:
        mock_sdk = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_sdk
        mock_sdk.messages.create.return_value = SimpleNamespace(content=response_content)
        client = ClaudeClient(api_key="fake-key")
    return client, mock_sdk


def test_protocol_is_satisfied_by_claude_client() -> None:
    with patch("textbook_companion.llm.anthropic"):
        client = ClaudeClient(api_key="fake-key")
    assert isinstance(client, LLMClient)


def test_default_model_is_opus_4_7() -> None:
    with patch("textbook_companion.llm.anthropic"):
        client = ClaudeClient(api_key="fake-key")
    assert client.model == "claude-opus-4-7"
    assert DEFAULT_MODEL == "claude-opus-4-7"


def test_chat_adds_cache_control_on_last_system_block() -> None:
    client, mock_sdk = _mock_claude_client([_block(type="text", text="hi")])

    client.chat(
        system="x" * 20_000,  # long enough to be well above the cache threshold
        messages=[{"role": "user", "content": "hello"}],
    )

    kwargs = mock_sdk.messages.create.call_args.kwargs
    system = kwargs["system"]
    assert isinstance(system, list) and len(system) == 1
    assert system[0]["type"] == "text"
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert kwargs["model"] == "claude-opus-4-7"


def test_chat_omits_cache_control_when_disabled() -> None:
    client, mock_sdk = _mock_claude_client([_block(type="text", text="hi")])

    client.chat(
        system="x" * 20_000,
        messages=[{"role": "user", "content": "hello"}],
        cache_system=False,
    )

    system = mock_sdk.messages.create.call_args.kwargs["system"]
    assert "cache_control" not in system[0]


def test_chat_returns_concatenated_text_blocks_only() -> None:
    client, _ = _mock_claude_client(
        [
            _block(type="text", text="hello "),
            _block(type="text", text="world"),
            _block(type="thinking", thinking="internal..."),  # should be ignored
        ]
    )

    out = client.chat(
        system="s" * 20_000,
        messages=[{"role": "user", "content": "q"}],
    )
    assert out == "hello world"


def test_chat_warns_when_system_below_cache_threshold(caplog: pytest.LogCaptureFixture) -> None:
    client, _ = _mock_claude_client([_block(type="text", text="hi")])

    with caplog.at_level(logging.WARNING, logger="textbook_companion.llm"):
        client.chat(system="short prompt", messages=[{"role": "user", "content": "q"}])

    assert any(
        "minimum for Opus 4.7 prompt caching" in rec.message for rec in caplog.records
    )


def test_chat_does_not_warn_when_caching_disabled(caplog: pytest.LogCaptureFixture) -> None:
    client, _ = _mock_claude_client([_block(type="text", text="hi")])

    with caplog.at_level(logging.WARNING, logger="textbook_companion.llm"):
        client.chat(
            system="short prompt",
            messages=[{"role": "user", "content": "q"}],
            cache_system=False,
        )

    assert not any(
        "minimum for Opus 4.7 prompt caching" in rec.message for rec in caplog.records
    )


def test_chat_does_not_warn_when_system_above_threshold(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, _ = _mock_claude_client([_block(type="text", text="hi")])

    # roughly 5K tokens at ~4 chars/token estimate
    big_system = "x" * (MIN_CACHE_TOKENS_OPUS_4_7 * 4 + 100)
    with caplog.at_level(logging.WARNING, logger="textbook_companion.llm"):
        client.chat(system=big_system, messages=[{"role": "user", "content": "q"}])

    assert not any(
        "minimum for Opus 4.7 prompt caching" in rec.message for rec in caplog.records
    )


# --- structured() --------------------------------------------------------


class Person(BaseModel):
    name: str
    age: int = Field(ge=0)


def test_structured_forces_tool_use_and_passes_schema() -> None:
    tool_name = _tool_name_for(Person)
    client, mock_sdk = _mock_claude_client(
        [_block(type="tool_use", name=tool_name, input={"name": "Ada", "age": 36})]
    )

    result = client.structured(
        system="You return structured data.",
        user="Extract: Ada, 36",
        schema=Person,
    )

    assert result == Person(name="Ada", age=36)

    kwargs = mock_sdk.messages.create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": tool_name}
    assert kwargs["tools"] == [
        {
            "name": tool_name,
            "description": "Record a validated Person object.",
            "input_schema": Person.model_json_schema(),
        }
    ]
    assert kwargs["messages"] == [{"role": "user", "content": "Extract: Ada, 36"}]
    assert kwargs["model"] == "claude-opus-4-7"


def test_structured_validates_through_pydantic() -> None:
    tool_name = _tool_name_for(Person)
    # Model returns age as a string; Pydantic coerces and/or rejects per field rules.
    client, _ = _mock_claude_client(
        [_block(type="tool_use", name=tool_name, input={"name": "Ada", "age": "36"})]
    )
    result = client.structured(system="s", user="u", schema=Person)
    assert result == Person(name="Ada", age=36)


def test_structured_raises_on_invalid_payload() -> None:
    tool_name = _tool_name_for(Person)
    client, _ = _mock_claude_client(
        [_block(type="tool_use", name=tool_name, input={"name": "Ada", "age": -1})]
    )
    with pytest.raises(Exception):  # Pydantic ValidationError, or wrapper
        client.structured(system="s", user="u", schema=Person)


def test_structured_raises_when_tool_use_missing() -> None:
    client, _ = _mock_claude_client([_block(type="text", text="I refuse.")])
    with pytest.raises(StructuredOutputError):
        client.structured(system="s", user="u", schema=Person)


def test_tool_name_for_sanitises_class_name() -> None:
    class Weird_Name_Thing(BaseModel):  # noqa: N801 — intentionally odd
        x: int

    name = _tool_name_for(Weird_Name_Thing)
    assert name.startswith("emit_")
    assert all(c.isalnum() or c == "_" for c in name)


# --- Live smoke test -----------------------------------------------------


@pytest.mark.live
def test_live_chat_roundtrip() -> None:
    """Real API call — skipped unless you pass `-m live` to pytest."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    client = ClaudeClient()
    out = client.chat(
        system=(
            "You are a terse test oracle. When the user says 'ping', reply with "
            "exactly the single word: pong. Do not add punctuation."
        ),
        messages=[{"role": "user", "content": "ping"}],
        cache_system=False,  # system prompt is tiny, skip the caching warning
    )
    assert "pong" in out.lower()


@pytest.mark.live
def test_live_structured_roundtrip() -> None:
    """Real API call — forced tool use returns a valid Pydantic object."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")

    client = ClaudeClient()
    person = client.structured(
        system="Extract a Person from the user's text. Use whatever values you see.",
        user="Her name is Ada Lovelace and she is 36.",
        schema=Person,
    )
    assert isinstance(person, Person)
    assert "ada" in person.name.lower()
    assert person.age == 36
