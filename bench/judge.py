"""Quality judging — hybrid: objective reference + LLM-judge for subjective.

Objective prompts ship with `expected_contains` (substrings the response
must contain) and optionally `expected_max_words` (length cap). These are
graded deterministically without any API call.

Subjective prompts ship with `judge_criteria` (what a strong model should
look for). We call a strong model with a strict rubric and parse a 1-5
score plus rationale.

Score semantics (consistent across modes):
    5 — fully correct / meets all criteria
    4 — minor issues, still useful
    3 — partially correct, mixed quality
    2 — significantly wrong / unhelpful
    1 — completely wrong / refused / empty
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal


JudgeKind = Literal["objective", "subjective"]


@dataclass(frozen=True)
class JudgeResult:
    score: int  # 1..5
    kind: JudgeKind
    rationale: str
    judge_model: str = ""  # empty for objective grades


# ─────────────────────────────────────────────────────────────────────────
# Objective grading — deterministic, no API call
# ─────────────────────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Lowercase + strip + collapse whitespace for forgiving substring match."""
    return re.sub(r"\s+", " ", s.lower().strip())


def grade_objective(response: str, entry: dict) -> JudgeResult:
    """Grade an objective response against expected_contains / expected_max_words.

    Score:
        5 if all expected substrings present AND length cap met (or no cap)
        3 if SOME expected substrings present
        1 if NO expected substrings present OR response is empty
    """
    if not response.strip():
        return JudgeResult(score=1, kind="objective", rationale="empty response")

    expected = entry.get("expected_contains", [])
    if not expected:
        # No reference -> can't grade objectively. Caller shouldn't ask but
        # we soften to 3 (neither pass nor fail).
        return JudgeResult(score=3, kind="objective", rationale="no expected_contains in corpus entry")

    norm_resp = _normalize(response)
    matched = [needle for needle in expected if _normalize(str(needle)) in norm_resp]
    coverage = len(matched) / len(expected)

    max_words = entry.get("expected_max_words")
    if max_words is not None:
        word_count = len(response.split())
        over_budget = word_count > max_words
    else:
        over_budget = False

    if coverage == 1.0 and not over_budget:
        return JudgeResult(
            score=5,
            kind="objective",
            rationale=f"matched {len(matched)}/{len(expected)} expected substrings, length ok",
        )
    if coverage == 1.0 and over_budget:
        return JudgeResult(
            score=4,
            kind="objective",
            rationale=f"matched all expected substrings but exceeded {max_words}-word cap",
        )
    if coverage > 0:
        return JudgeResult(
            score=3,
            kind="objective",
            rationale=f"matched {len(matched)}/{len(expected)} expected substrings",
        )
    return JudgeResult(
        score=1,
        kind="objective",
        rationale=f"matched 0/{len(expected)} expected substrings",
    )


# ─────────────────────────────────────────────────────────────────────────
# Subjective grading — LLM-as-judge
# ─────────────────────────────────────────────────────────────────────────

_JUDGE_SYSTEM_PROMPT = """You are a strict, impartial grader for LLM responses.

You will receive:
  1. The original prompt.
  2. The criteria the response must meet.
  3. The response to grade.

Score the response on a 1-5 integer scale:
  5 = Fully meets every criterion. No improvements needed.
  4 = Meets criteria with minor issues that don't impair usefulness.
  3 = Partial — some criteria met, some not.
  2 = Significantly fails criteria.
  1 = Completely fails / empty / off-topic / refusal.

Return ONLY a JSON object with exactly these keys:
  {"score": <integer 1-5>, "rationale": "<one-sentence justification>"}
"""


def _parse_judge_output(text: str) -> tuple[int, str]:
    """Extract (score, rationale) from a judge response. Robust to chatter."""
    # Try strict JSON first.
    try:
        obj = json.loads(text.strip())
        score = int(obj.get("score", 0))
        rationale = str(obj.get("rationale", ""))
        if 1 <= score <= 5:
            return score, rationale
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Fallback: find first {...} block.
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group(0))
            score = int(obj.get("score", 0))
            rationale = str(obj.get("rationale", ""))
            if 1 <= score <= 5:
                return score, rationale
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    # Last-ditch: find any "score: N" pattern.
    m = re.search(r"score['\"]?\s*[:=]\s*(\d)", text, re.IGNORECASE)
    if m:
        score = int(m.group(1))
        if 1 <= score <= 5:
            return score, "(score parsed from non-JSON output)"

    return 0, f"could not parse judge output: {text[:200]}"


async def grade_subjective(
    response: str,
    entry: dict,
    judge_model: str = "anthropic/claude-3.5-sonnet",
) -> JudgeResult:
    """Grade a subjective response via LLM-as-judge.

    On parse failure or empty response, returns score=1 to penalize.
    """
    if not response.strip():
        return JudgeResult(
            score=1, kind="subjective", rationale="empty response",
            judge_model=judge_model,
        )

    criteria = entry.get("judge_criteria", "Response should be correct, complete, and concise.")
    user_msg = (
        f"PROMPT:\n{entry['prompt']}\n\n"
        f"CRITERIA:\n{criteria}\n\n"
        f"RESPONSE TO GRADE:\n{response}\n\n"
        f"Return JSON only."
    )

    import litellm  # lazy import — tests use FakeRouter and never reach this path

    judge_response = await litellm.acompletion(
        model=judge_model,
        messages=[
            {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.0,
        max_tokens=200,
    )
    judge_text = judge_response.choices[0].message.content or ""
    score, rationale = _parse_judge_output(judge_text)
    if score == 0:
        return JudgeResult(
            score=1, kind="subjective",
            rationale=f"judge parse failure: {rationale}",
            judge_model=judge_model,
        )
    return JudgeResult(
        score=score, kind="subjective", rationale=rationale,
        judge_model=judge_model,
    )


async def grade(
    response: str,
    entry: dict,
    judge_model: str = "anthropic/claude-3.5-sonnet",
) -> JudgeResult:
    """Dispatch to the right grader based on entry['kind']."""
    kind = entry.get("kind", "subjective")
    if kind == "objective":
        return grade_objective(response, entry)
    return await grade_subjective(response, entry, judge_model=judge_model)
