"""Tests for live call mode: question gate, streaming URL, prompts, settings."""

from __future__ import annotations

import asyncio

import pytest

from src import live_session as live_mod
from src import server
from src.live_session import LiveSession
from src.llm.gate import heuristic_is_question
from src.llm.prompts import build_live_system
from src.settings import Settings
from src.stt.deepgram_stream import DeepgramStream


class TestHeuristicQuestion:
    def test_explicit_question_mark(self) -> None:
        assert heuristic_is_question("What is your greatest weakness?")

    def test_indirect_interview_prompts(self) -> None:
        assert heuristic_is_question("Tell me about a time you failed.")
        assert heuristic_is_question("Walk me through your approach.")
        assert heuristic_is_question("Describe a hard bug you fixed.")

    def test_interrogative_without_question_mark(self) -> None:
        assert heuristic_is_question("How would you scale this")

    def test_non_questions(self) -> None:
        assert not heuristic_is_question("Thanks, that makes sense.")
        assert not heuristic_is_question("Okay, great.")
        assert not heuristic_is_question("")

    def test_interrogative_midsentence(self) -> None:
        assert heuristic_is_question("So, can you explain how indexes work")


class TestDeepgramStreamURL:
    def test_url_has_streaming_params(self) -> None:
        url = DeepgramStream(api_key="x", model="nova-3", sample_rate=16000)._url()
        assert url.startswith("wss://api.deepgram.com/v1/listen?")
        assert "encoding=linear16" in url
        assert "sample_rate=16000" in url
        assert "interim_results=true" in url
        assert "utterance_end_ms=1000" in url
        assert "model=nova-3" in url


class TestLivePrompt:
    def test_context_is_embedded(self) -> None:
        system = build_live_system("CODING", "Senior engineer", "Interviewer: Two sum?")
        assert "Interviewer: Two sum?" in system
        assert "Senior engineer" in system
        assert "web_search" in system

    def test_empty_context_placeholder(self) -> None:
        system = build_live_system("GENERAL", "", "")
        assert "no prior context" in system


class TestLiveSettings:
    def test_defaults(self) -> None:
        s = Settings()
        assert s.hotkey_call == "ctrl+;"
        assert s.live_gate_model == "claude-haiku-4-5"
        assert s.enable_web_search is True
        assert s.live_context_utterances == 12


class _FakeLiveLLM:
    """LLM provider exposing the live-mode streaming method."""

    name = "fake-live"

    async def stream_live_answer(self, question, context, mode, persona, web_search, on_context=None):
        if on_context is not None:
            on_context({"kind": "query", "text": "two sum complexity", "url": ""})
            on_context({"kind": "source", "text": "Time complexity", "url": "https://example.com/big-o"})
        for tok in ("Hello ", "world"):
            yield tok


class _FakeBatchLLM:
    """LLM provider without stream_live_answer — exercises the fallback path."""

    name = "fake-batch"

    async def stream_answer(self, transcript, mode, persona):
        assert "QUESTION:" in transcript  # context+question were threaded in
        for tok in ("Fallback ", "answer"):
            yield tok


class TestLiveAnswerFlow:
    @pytest.mark.asyncio
    async def test_streams_answer_to_server(self, monkeypatch) -> None:
        monkeypatch.setattr(live_mod, "get_llm", lambda *a, **k: _FakeLiveLLM())
        server.new_session()
        sess = LiveSession(Settings(), asyncio.get_event_loop())
        await sess._answer("What is 2+2?")
        last = server._state["answers"][-1]
        assert last["text"] == "Hello world"
        assert last["status"] == "DONE"
        assert last["question"] == "What is 2+2?"
        # web-search context was captured and surfaced for the Context tab
        ctx = server._state["context"]
        assert any(c["kind"] == "query" for c in ctx)
        assert any(c["kind"] == "source" and c["url"] for c in ctx)

    @pytest.mark.asyncio
    async def test_falls_back_when_no_live_method(self, monkeypatch) -> None:
        monkeypatch.setattr(live_mod, "get_llm", lambda *a, **k: _FakeBatchLLM())
        server.new_session()
        sess = LiveSession(Settings(), asyncio.get_event_loop())
        sess._context.append("Interviewer: Explain TCP.")
        await sess._answer("Explain TCP.")
        last = server._state["answers"][-1]
        assert last["text"] == "Fallback answer"
        assert last["status"] == "DONE"

    @pytest.mark.asyncio
    async def test_force_answer_inactive_is_noop(self) -> None:
        sess = LiveSession(Settings(), asyncio.get_event_loop())
        # Not active → must not raise or schedule anything
        sess.force_answer()
        assert not sess.is_active
