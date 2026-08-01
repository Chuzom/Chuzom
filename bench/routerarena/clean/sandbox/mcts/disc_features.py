# SPDX-License-Identifier: MIT
"""Shared feature functions for the discriminator — imported by BOTH the
Chuzom-venv generator (synthetic) and the RA-venv trainer (RA-150), so features
are computed by identical code on both sides (parity is essential for transfer).

Pure stdlib (re) — no venv-specific deps.
"""
from __future__ import annotations

import re

_BOX = re.compile(r"\\boxed\{([^{}]+)\}")
_FINAL = re.compile(r"(?:final answer|answer)\s*[:\-]?\s*\**([A-Za-z0-9][^\n.*]{0,60})", re.I)
# non-English scripts: CJK, Hiragana/Katakana, Cyrillic, Greek, Arabic, Hebrew, Devanagari
_NONENG = re.compile(r"[Ͱ-ϿЀ-ӿ֐-׿؀-ۿ"
                     r"ऀ-ॿ぀-ヿ㐀-䶿一-鿿가-힯]")
_CODE = re.compile(r"```|\bdef \b|\breturn \b|\bprint\(|for .*in range|\bimport \b|=>|\{\s*$", re.M)
_MATH = re.compile(r"\d\s*[+\-*/^=×÷]|\bmod\b|determinant|matrix|\bcompute\b|\bevaluate\b|\bsum\b", re.I)

# canonical feature order (both sides must match)
FEATURE_NAMES = ["coherence", "agree_qwen", "spread3", "nonenglish",
                 "q_len", "has_code", "has_math", "cheap_ext_len"]


def norm_ans(raw):
    """Generic short-answer normalizer (identical to council_killgate.norm_ans)."""
    t = raw or ""
    m = _BOX.findall(t)
    if m:
        return m[-1].strip().lower().replace(" ", "")
    m = _FINAL.findall(t)
    if m:
        return m[-1].strip().lower().rstrip(".)").replace(" ", "")
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if lines:
        last = lines[-1]
        mc = re.match(r"^\(?([A-Ea-e])\)?[\).:\s]", last)
        if mc:
            return mc.group(1).lower()
        return last[:60].lower().replace(" ", "")
    return ""


def build_features(coherence, cheap_ext, qwen_ext, mistral_ext, query):
    """Return an 8-dim feature list in FEATURE_NAMES order."""
    exts = [e for e in (cheap_ext, qwen_ext, mistral_ext) if e]
    spread = len(set(exts)) if exts else 1
    agree = 1 if (cheap_ext and cheap_ext == qwen_ext) else 0
    noneng = 1 if _NONENG.search(query or "") else 0
    return [
        float(coherence),
        float(agree),
        float(spread),
        float(noneng),
        float(min(len(query or ""), 4000)),
        1.0 if _CODE.search(query or "") else 0.0,
        1.0 if _MATH.search(query or "") else 0.0,
        float(min(len(cheap_ext or ""), 200)),
    ]
