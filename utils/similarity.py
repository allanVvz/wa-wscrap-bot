"""Reusable similarity helpers (TF-IDF, fuzzy matching, hybrid ranking)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class RankedMatch:
    index: int
    tfidf_score: float
    lexical_score: Optional[float] = None
    forced: bool = False

    @property
    def combined_score(self) -> float:
        bonus = (self.lexical_score or 0.0) / 100.0 * 0.05
        return self.tfidf_score + bonus


class SimilarityEngineTFIDF:
    """Thin wrapper around a TF-IDF vectorizer for repeated searches."""

    def __init__(self, **vectorizer_kwargs):
        kwargs = {
            "analyzer": "char_wb",
            "ngram_range": (3, 5),
            "lowercase": False,
        }
        kwargs.update(vectorizer_kwargs)
        self._vectorizer = TfidfVectorizer(**kwargs)
        self._matrix = None
        self._fitted = False

    @property
    def vectorizer(self) -> TfidfVectorizer:
        return self._vectorizer

    def fit(self, corpus: Sequence[str]) -> None:
        if not corpus:
            self._matrix = None
            self._fitted = False
            return
        self._matrix = self._vectorizer.fit_transform(corpus)
        self._fitted = True

    def search(
        self,
        query: str,
        top_k: int = 5,
        *,
        candidate_indices: Optional[Sequence[int]] = None,
    ) -> List[Tuple[int, float]]:
        if not self._fitted or not query:
            return []
        query_vec = self._vectorizer.transform([query])
        matrix = self._matrix
        if matrix is None or matrix.shape[0] == 0:
            return []

        if candidate_indices is not None:
            if not candidate_indices:
                return []
            matrix = matrix[candidate_indices]

        similarities = cosine_similarity(query_vec, matrix).ravel()
        if similarities.size == 0:
            return []

        # argsort descending
        top_k = max(top_k, 1)
        idx_sorted = np.argsort(-similarities)[:top_k]
        results: List[Tuple[int, float]] = []
        for pos in idx_sorted:
            score = float(similarities[pos])
            if score <= 0:
                continue
            if candidate_indices is not None:
                doc_index = candidate_indices[pos]
            else:
                doc_index = int(pos)
            results.append((doc_index, score))
        return results


class LexicalSimilarity:
    """Wrapper for optional fuzzy matching using rapidfuzz."""

    def __init__(self) -> None:
        try:
            from rapidfuzz import fuzz, process  # type: ignore
        except ImportError:  # pragma: no cover - optional dependency
            self._available = False
            self._process = None
            self._scorer = None
        else:
            self._available = True
            self._process = process
            self._scorer = fuzz.WRatio

    @property
    def available(self) -> bool:
        return bool(self._available)

    def candidates(
        self,
        query: str,
        corpus: Sequence[str],
        top_k: int = 5,
    ) -> List[Tuple[int, float]]:
        if not self.available or not query:
            return []
        if not corpus:
            return []
        assert self._process is not None and self._scorer is not None
        results = self._process.extract(
            query,
            corpus,
            scorer=self._scorer,
            limit=top_k,
        )
        matches: List[Tuple[int, float]] = []
        for choice, score, index in results:
            if not choice:
                continue
            matches.append((int(index), float(score)))
        return matches


class HybridRanker:
    """Two-stage ranking combining lexical and TF-IDF similarity."""

    def __init__(
        self,
        corpus: Sequence[str],
        tfidf_engine: SimilarityEngineTFIDF,
        *,
        lexical_engine: Optional[LexicalSimilarity] = None,
        fuzzy_accept_threshold: float = 85.0,
        fuzzy_min_threshold: float = 70.0,
        high_conf_threshold: float = 0.25,
        medium_conf_threshold: float = 0.15,
    ) -> None:
        self._corpus = list(corpus)
        self._tfidf = tfidf_engine
        self._lexical = lexical_engine
        self.fuzzy_accept_threshold = fuzzy_accept_threshold
        self.fuzzy_min_threshold = fuzzy_min_threshold
        self.high_conf_threshold = high_conf_threshold
        self.medium_conf_threshold = medium_conf_threshold

    def search(self, query: str, top_k: int = 3) -> List[RankedMatch]:
        if not query:
            return []

        lexical_map = {}
        candidate_indices: Optional[List[int]] = None
        if self._lexical and self._lexical.available:
            lexical_hits = self._lexical.candidates(
                query,
                self._corpus,
                top_k=max(top_k * 4, 10),
            )
            lexical_map = {idx: score for idx, score in lexical_hits}
            candidate_indices = [
                idx for idx, score in lexical_hits if score >= self.fuzzy_min_threshold
            ]
            if not candidate_indices:
                candidate_indices = None
        else:
            lexical_hits = []

        tfidf_hits = self._tfidf.search(
            query,
            top_k=max(top_k * 4, 10),
            candidate_indices=candidate_indices,
        )

        ranked = {}
        for idx, score in tfidf_hits:
            ranked[idx] = RankedMatch(
                index=idx,
                tfidf_score=float(score),
                lexical_score=lexical_map.get(idx),
                forced=False,
            )

        for idx, score in lexical_hits:
            if score >= self.fuzzy_accept_threshold and idx not in ranked:
                ranked[idx] = RankedMatch(
                    index=idx,
                    tfidf_score=self.high_conf_threshold,
                    lexical_score=score,
                    forced=True,
                )

        ranked_list = sorted(
            ranked.values(),
            key=lambda item: item.combined_score,
            reverse=True,
        )
        return ranked_list[:top_k]
