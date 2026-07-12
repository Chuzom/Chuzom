# SPDX-License-Identifier: MIT
"""Self-generated, RA-disjoint synthetic corpus for the discriminator.

~80% computed-answer traps (math/logic/code/string; from traps_gen) + ~20%
multilingual lexicon items in NON-LATIN scripts (computable gold, and they make
the 'non-English' feature fire). All gold is self-computed / self-defined — no RA
data, no dataset lookup. Difficulty is varied so the cheap model has a real
success/fail gradient (needed to train a failure discriminator).
"""
from __future__ import annotations

import random
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memorytree"))
import traps_gen as TG  # noqa: E402

# HARD parameterizations — chosen to push deepseek-v4-flash to ~25-40% failure so
# the discriminator sees enough failure examples (the [0.10,0.50] balance rule).
_HARD = [
    (TG.bigmul, 5), (TG.bigmul, 6),
    (TG.determinant, 4), (TG.determinant, 5),
    (TG.modexp, 6), (TG.modexp, 8),
    (TG.nested, 4), (TG.nested, 5),
    (TG.count_occ, 120), (TG.count_occ, 180),
    (TG.chain, 20), (TG.chain, 28),
    (TG.stack_sim, 30), (TG.stack_sim, 44),
    (TG.code_trace, 9), (TG.code_trace, 13),
    (TG.sort_kth, 14), (TG.sequence_next, 6),
    (TG.string_op, 20), (TG.determinant, 4),
]


def _hard_traps(r, n):
    out, seen, i = [], set(), 0
    while len(out) < n:
        fn, param = r.choice(_HARD)
        q, a = fn(r, param)
        if q in seen:
            continue
        seen.add(q)
        out.append({"id": f"trap-{i:05d}", "gen": fn.__name__, "kind": "trap",
                    "prompt": q + " Put your final answer in \\boxed{}.", "answer": a})
        i += 1
    return out

# Small self-authored lexicon in non-Latin scripts (script → trivially detectable
# as non-English). english : {LangName: foreign}. Mix of common + rarer to create
# a failure gradient for the cheap model.
LEX = [
    ("water", {"Chinese": "水", "Russian": "вода", "Greek": "νερό", "Japanese": "水"}),
    ("mountain", {"Chinese": "山", "Russian": "гора", "Greek": "βουνό", "Japanese": "山"}),
    ("friend", {"Chinese": "朋友", "Russian": "друг", "Greek": "φίλος", "Japanese": "友達"}),
    ("book", {"Chinese": "书", "Russian": "книга", "Greek": "βιβλίο", "Japanese": "本"}),
    ("fire", {"Chinese": "火", "Russian": "огонь", "Greek": "φωτιά", "Japanese": "火"}),
    ("bird", {"Chinese": "鸟", "Russian": "птица", "Greek": "πουλί", "Japanese": "鳥"}),
    ("bridge", {"Chinese": "桥", "Russian": "мост", "Greek": "γέφυρα", "Japanese": "橋"}),
    ("shadow", {"Chinese": "影子", "Russian": "тень", "Greek": "σκιά", "Japanese": "影"}),
    ("honey", {"Chinese": "蜂蜜", "Russian": "мёд", "Greek": "μέλι", "Japanese": "蜂蜜"}),
    ("winter", {"Chinese": "冬天", "Russian": "зима", "Greek": "χειμώνας", "Japanese": "冬"}),
    ("silence", {"Chinese": "沉默", "Russian": "тишина", "Greek": "σιωπή", "Japanese": "沈黙"}),
    ("copper", {"Chinese": "铜", "Russian": "медь", "Greek": "χαλκός", "Japanese": "銅"}),
    ("harvest", {"Chinese": "收获", "Russian": "урожай", "Greek": "συγκομιδή", "Japanese": "収穫"}),
    ("thunder", {"Chinese": "雷", "Russian": "гром", "Greek": "βροντή", "Japanese": "雷"}),
    ("compass", {"Chinese": "指南针", "Russian": "компас", "Greek": "πυξίδα", "Japanese": "羅針盤"}),
    ("wisdom", {"Chinese": "智慧", "Russian": "мудрость", "Greek": "σοφία", "Japanese": "知恵"}),
]


_LANGS = ["Chinese", "Russian", "Greek", "Japanese"]


def _multilingual(r):
    """A 1-3 word foreign sequence (one language) → English meanings in order.
    Non-Latin script (feature fires), computable gold, many unique combos."""
    lang = r.choice(_LANGS)
    k = r.randint(1, 3)
    picks = r.sample(LEX, k)
    foreign = " ".join(langs[lang] for _, langs in picks)
    gold = " ".join(eng for eng, _ in picks)
    if k == 1:
        q = (f"What is the English meaning of the {lang} word '{foreign}'? "
             f"Answer with a single English word in \\boxed{{}}.")
    else:
        q = (f"Translate this {lang} sequence to English, keeping the word order: "
             f"'{foreign}'. Put the {k} English words (space-separated) in \\boxed{{}}.")
    return q, gold


def generate(n=2000, seed=20260707):
    r = random.Random(seed)
    n_ml = int(round(n * 0.20))
    n_tr = n - n_ml
    out = _hard_traps(r, n_tr)
    seen = set()
    i = 0
    while len([o for o in out if o["kind"] == "ml"]) < n_ml:
        q, a = _multilingual(r)
        if q in seen:
            continue
        seen.add(q)
        out.append({"id": f"ml-{i:05d}", "gen": "multilingual", "prompt": q,
                    "answer": a, "kind": "ml"})
        i += 1
    r.shuffle(out)
    return out


if __name__ == "__main__":
    import json
    from collections import Counter
    recs = generate(40)
    print("kinds:", dict(Counter(x["kind"] for x in recs)))
    print("gens:", dict(Counter(x["gen"] for x in recs)))
    for x in recs[:3] + [o for o in recs if o["kind"] == "ml"][:2]:
        print(json.dumps({k: x[k] for k in ("gen", "prompt", "answer")}, ensure_ascii=False))
