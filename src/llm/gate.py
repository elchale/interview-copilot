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
import re

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
    "You are a real-time gate inside an interview copilot. The interview may be of ANY kind — "
    "technical, behavioral, academic, philosophical, domain-specific, casual — so do not assume a "
    "coding context. The interviewer may speak ANY language (often Spanish or English); classify "
    "regardless of language and keep 'question' in the interviewer's original language.\n"
    "Decide whether the LATEST line from the interviewer requires the candidate to respond NOW. "
    "Set needs_answer=true for any of: a direct question; an open prompt ('tell me about...', "
    "'cuéntame...'); a request; OR a CHALLENGE / TASK — including imperative design, system-design, "
    "coding, or estimation problems ('Design a rate limiter...', 'Diseña un...', 'Implement...', "
    "'Walk me through how you'd scale...'). An imperative task with no question mark is still "
    "needs_answer=true. Return needs_answer=false ONLY for small talk, acknowledgements, filler, or "
    "the interviewer thinking aloud.\n"
    "When needs_answer is true, set 'question' to the core question or task the candidate must "
    "answer. Strip leading preamble, filler ('so', 'um', 'you know', 'bueno', 'este'), surrounding "
    "narration, and trailing chatter — but KEEP all substantive parts: if the prompt has multiple "
    "parts or sub-questions (e.g. 'Design X. Then explain the trade-off and what breaks first'), "
    "preserve every part. Trim padding, never substance."
)

# Filler/preamble that wraps a spoken question — stripped so the displayed question is just
# the question, not the surrounding narration.
_FILLER_LEAD = re.compile(
    r"^(?:\s*(?:so|and|but|well|ok|okay|um|uh|er|yeah|now|right|like|anyway|alright|"
    r"you know|i mean|i guess|i suppose|i wonder|i was wondering|let me ask|"
    r"(?:my |the )?question (?:really |actually |basically |then |now |i guess )*"
    r"(?:is|becomes)|here'?s (?:my|the) question)"
    r"\b[\s,]*)+",
    re.IGNORECASE,
)
_FILLER_TAIL = re.compile(
    r"[\s,]*(?:you know|right|okay|ok|yeah|i guess|or something|you see|hmm|huh)[\s,.?!]*$",
    re.IGNORECASE,
)


def extract_question(text: str) -> str:
    """Pull just the core question/prompt out of a spoken utterance, dropping padding.

    Picks the sentence carrying the question (the one ending in '?', else the last
    sentence) and trims leading preamble and trailing chatter. Best-effort and
    cosmetic — the full context still drives the actual answer.
    """
    t = text.strip()
    if not t:
        return text
    q = t.rfind("?")
    if q != -1:
        prev_end = max(t.rfind(".", 0, q), t.rfind("!", 0, q), t.rfind("?", 0, q))
        seg = t[prev_end + 1 : q + 1].strip()
    else:
        parts = re.split(r"(?<=[.!?])\s+", t)
        seg = parts[-1].strip() if parts else t
    seg = _FILLER_LEAD.sub("", seg).strip()
    seg = _FILLER_TAIL.sub("", seg).strip()
    if seg and seg[0].islower():
        seg = seg[0].upper() + seg[1:]
    return seg or t.strip()


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
            return True, extract_question(utterance)
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
