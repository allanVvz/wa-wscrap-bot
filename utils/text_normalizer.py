"""Utility helpers for lightweight text normalization.

These functions avoid heavy NLP dependencies so they can be reused in
API paths or other latency-sensitive flows.
"""
from __future__ import annotations

import re
import string
from typing import Iterable, List

try:
    from unidecode import unidecode
except ImportError:  # pragma: no cover - optional dependency
    unidecode = None  # type: ignore


_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_TABLE = str.maketrans({ch: " " for ch in string.punctuation})
_STOPWORDS_PT = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "para",
    "por",
    "que",
    "se",
    "sem",
    "uma",
    "umas",
    "um",
    "uns",
}


def _strip_accents(text: str) -> str:
    if not text:
        return ""
    if unidecode is not None:
        return unidecode(text)
    # Basic fallback removing combining marks when unidecode is missing
    normalized = (
        text.replace("á", "a")
        .replace("à", "a")
        .replace("ã", "a")
        .replace("â", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("õ", "o")
        .replace("ú", "u")
        .replace("ç", "c")
    )
    return normalized


def normalize_basic(text: str) -> str:
    """Normalizes text for similarity comparisons.

    Steps:
    1. Lowercase input.
    2. Remove accents when possible.
    3. Replace punctuation by spaces and collapse whitespace.
    """
    if not text:
        return ""
    lowered = text.casefold()
    stripped = _strip_accents(lowered)
    no_punct = stripped.translate(_PUNCT_TABLE)
    collapsed = _WHITESPACE_RE.sub(" ", no_punct)
    return collapsed.strip()


def strip_stopwords_pt(tokens: Iterable[str]) -> List[str]:
    """Removes a minimal set of Portuguese stopwords from the iterable."""
    return [token for token in tokens if token not in _STOPWORDS_PT]
