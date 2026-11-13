"""OCR quality metrics (CER/WER, Vietnamese diacritics, key fields). No deps."""

from __future__ import annotations

import re
import unicodedata


def normalize(text: str) -> str:
    """NFC, collapse whitespace, drop markdown decoration Docling may add."""
    text = unicodedata.normalize("NFC", text or "")
    text = re.sub(r"[#*_`|>]+", " ", text)
    text = re.sub(r"-{3,}", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _levenshtein(a: list, b: list) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(reference: str, hypothesis: str) -> float:
    ref, hyp = normalize(reference), normalize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(list(ref), list(hyp)) / len(ref)


def wer(reference: str, hypothesis: str) -> float:
    ref, hyp = normalize(reference).split(), normalize(hypothesis).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(ref, hyp) / len(ref)


def _strip_marks(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    base = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", base).replace("đ", "d").replace("Đ", "D")


def diacritic_accuracy(reference: str, hypothesis: str) -> float | None:
    """Share of reference words carrying Vietnamese marks that appear verbatim.

    Words are matched by their mark-stripped form, so this isolates "were the
    diacritics right?" from "was the word found at all?".
    """
    ref_words = [
        w for w in normalize(reference).lower().split() if _strip_marks(w) != w
    ]
    if not ref_words:
        return None
    hyp_words = normalize(hypothesis).lower().split()
    by_base: dict[str, set[str]] = {}
    for w in hyp_words:
        by_base.setdefault(_strip_marks(w), set()).add(w)
    found = matched = 0
    for w in ref_words:
        cands = by_base.get(_strip_marks(w))
        if cands:
            found += 1
            matched += w in cands
    return matched / found if found else 0.0


def field_recall(fields: list[str], hypothesis: str) -> float | None:
    """Fraction of exact key fields (amounts, dates, doc numbers) found verbatim."""
    if not fields:
        return None
    hyp = normalize(hypothesis)
    compact = hyp.replace(" ", "")
    hits = sum(
        1
        for f in fields
        if normalize(f) in hyp or normalize(f).replace(" ", "") in compact
    )
    return hits / len(fields)


def word_recall(reference: str, hypothesis: str) -> float:
    """Order-independent share of reference words recognised verbatim.

    Complements CER/WER, which also penalise reading order (e.g. a rotated
    page whose words are right but whose lines come back in another order).
    """
    from collections import Counter

    ref = Counter(normalize(reference).split())
    if not ref:
        return 1.0
    hyp = Counter(normalize(hypothesis).split())
    return sum(min(n, hyp[w]) for w, n in ref.items()) / sum(ref.values())
