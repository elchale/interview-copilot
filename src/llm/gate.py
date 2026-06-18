"""Question-detection gate for live call mode.

Two tiers, tuned to never miss a question while keeping latency and cost low:

1. An instant, free heuristic that catches explicit questions and common
   interview prompts ("tell me about...", "walk me through...").
2. A cheap, fast LLM (Haiku by default) that classifies everything ambiguous,
   catching indirect questions the heuristic misses.
"""

from __future__ import annotations

import json
import logging

import anthropic

logger = logging.getLogger(__name__)

DEFAULT_GATE_MODEL = "claude-haiku-4-5"

# Tokens that signal a question only when the line STARTS with them. Matching these
# mid-sentence caused false positives (e.g. "let me share my screen" → "share"), so
# bare verbs are start-only; anything ambiguous falls through to the LLM gate.
_START_TOKENS: tuple[str, ...] = (
    "what", "why", "how", "when", "where", "who", "which", "whose", "whom",
    "what's", "how's", "is there", "are there",
    "tell me", "walk me", "describe", "explain", "give me", "share",
    "talk about", "let's", "suppose", "imagine", "consider", "what if", "how about",
)

# Polite request lead-ins that signal a question even mid-sentence ("so, can you...").
_ANYWHERE_PHRASES: tuple[str, ...] = (
    "can you", "could you", "would you", "will you", "do you", "did you",
    "have you", "are you", "what do you", "how would you", "how do you",
)

_GATE_SCHEMA = {
    "type": "object",
    "properties": {
        "needs_answer": {"type": "boolean"},
        "question": {"type": "string"},
    },
    "required": ["needs_answer", "question"],
    "additionalProperties": False,
}

_GATE_SYSTEM = (
    "You are a real-time gate inside an interview copilot. Decide whether the LATEST line from the "
    "interviewer requires the candidate to respond NOW — a question, a prompt like 'tell me about...', "
    "a request, a challenge, or a coding/design problem. Return needs_answer=false for small talk, "
    "acknowledgements, filler, or the interviewer thinking aloud. When needs_answer is true, set "
    "'question' to the exact thing the candidate should answer."
)


def heuristic_is_question(text: str) -> bool:
    """Fast, free check for explicit questions and common interview prompts.

    Conservative on purpose: a miss here just routes the line to the smart LLM gate,
    but a false positive forces an unwanted answer — so we only fast-path strong signals.
    """
    t = text.strip().lower()
    if not t:
        return False
    if t.endswith("?"):
        return True
    if any(t.startswith(k) for k in _START_TOKENS):
        return True
    padded = f" {t} "
    return any(f" {k} " in padded for k in _ANYWHERE_PHRASES)


class QuestionGate:
    """Decides whether an utterance needs an answer, cheaply and fast."""

    def __init__(self, api_key: str, model: str | None = None) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model or DEFAULT_GATE_MODEL

    async def classify(self, context: str, utterance: str) -> tuple[bool, str]:
        """Return (needs_answer, question_text). Heuristic first, LLM for ambiguous cases."""
        if heuristic_is_question(utterance):
            return True, utterance
        try:
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=200,
                system=_GATE_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": f"CONTEXT:\n{context}\n\nLATEST LINE:\n{utterance}",
                }],
                output_config={"format": {"type": "json_schema", "schema": _GATE_SCHEMA}},
            )
            text = next((b.text for b in resp.content if b.type == "text"), "")
            data = json.loads(text)
            return bool(data.get("needs_answer")), (data.get("question") or utterance)
        except Exception as e:
            logger.warning("Question gate classify failed: %s", e)
            return False, utterance
