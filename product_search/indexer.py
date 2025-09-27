"""Product search index built on top of product_lookup utilities."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import List, Optional

from product_lookup import Product, Sku, fetch_products
from utils.text_normalizer import normalize_basic
from utils.similarity import (
    HybridRanker,
    LexicalSimilarity,
    RankedMatch,
    SimilarityEngineTFIDF,
)


class ProductIndexUnavailable(RuntimeError):
    """Raised when the catalog cannot be consulted."""


@dataclass
class ProductDocument:
    product: Product
    sku: Optional[Sku]
    purchase_url: Optional[str]
    label: str


@dataclass
class ProductIndex:
    documents: List[str]
    metadata: List[ProductDocument]
    tfidf: SimilarityEngineTFIDF
    ranker: HybridRanker
    built_at: float


@dataclass
class ProductMatch:
    label: str
    purchase_url: Optional[str]
    product: Product
    sku: Optional[Sku]
    tfidf_score: float
    lexical_score: Optional[float]
    forced: bool


@dataclass
class ProductSearchResult:
    matches: List[ProductMatch]
    confidence: str
    error: Optional[str] = None


_INDEX_CACHE: Optional[ProductIndex] = None

# Thresholds (can be overridden by env vars if needed)
_DEF_PRODUCT_INDEX_TTL = 600.0
_HIGH_CONF_THRESHOLD = 0.25
_MEDIUM_CONF_THRESHOLD = 0.15
_FUZZY_ACCEPT_THRESHOLD = 85.0
_FUZZY_MIN_THRESHOLD = 70.0


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _ensure_purchase_url(product: Product, sku: Optional[Sku]) -> Optional[str]:
    if sku and sku.purchase_url:
        return sku.purchase_url
    if product.url:
        return product.url
    if sku and sku.token:
        return sku.token
    return None


def _compose_label(product: Product, sku: Optional[Sku]) -> str:
    if sku and sku.title:
        return sku.title
    if product.name:
        return product.name
    return f"Produto {product.id}"


def _compose_document_text(product: Product, sku: Optional[Sku]) -> str:
    parts = [product.name, product.slug]
    if product.sku:
        parts.append(product.sku)
    if sku:
        parts.extend([sku.title, sku.sku or ""])
    return normalize_basic(" ".join(filter(None, parts)))


def _build_product_index(debug: bool = False) -> ProductIndex:
    try:
        products = fetch_products()
    except RuntimeError as exc:
        raise ProductIndexUnavailable(str(exc)) from exc
    except Exception as exc:  # pragma: no cover - catalog issues
        raise ProductIndexUnavailable(f"Erro ao consultar catálogo: {exc}") from exc

    documents: List[str] = []
    metadata: List[ProductDocument] = []

    for product in products:
        if not product:
            continue
        has_skus = False
        for sku in product.skus:
            doc_text = _compose_document_text(product, sku)
            if not doc_text:
                continue
            documents.append(doc_text)
            metadata.append(
                ProductDocument(
                    product=product,
                    sku=sku,
                    purchase_url=_ensure_purchase_url(product, sku),
                    label=_compose_label(product, sku),
                )
            )
            has_skus = True
        if not has_skus:
            doc_text = _compose_document_text(product, None)
            if not doc_text:
                continue
            documents.append(doc_text)
            metadata.append(
                ProductDocument(
                    product=product,
                    sku=None,
                    purchase_url=_ensure_purchase_url(product, None),
                    label=_compose_label(product, None),
                )
            )

    tfidf = SimilarityEngineTFIDF()
    tfidf.fit(documents)

    lexical = LexicalSimilarity()
    if not lexical.available:
        lexical = None

    ranker = HybridRanker(
        documents,
        tfidf,
        lexical_engine=lexical,
        fuzzy_accept_threshold=_FUZZY_ACCEPT_THRESHOLD,
        fuzzy_min_threshold=_FUZZY_MIN_THRESHOLD,
        high_conf_threshold=_HIGH_CONF_THRESHOLD,
        medium_conf_threshold=_MEDIUM_CONF_THRESHOLD,
    )

    if debug:
        print(
            f"[DEBUG] Produto indexado: {len(documents)} documentos, "
            f"lexical={'on' if lexical else 'off'}"
        )

    return ProductIndex(
        documents=documents,
        metadata=metadata,
        tfidf=tfidf,
        ranker=ranker,
        built_at=time.time(),
    )


def get_or_build_product_index(debug: bool = False) -> ProductIndex:
    global _INDEX_CACHE
    ttl = _env_float("PRODUCT_INDEX_TTL", _DEF_PRODUCT_INDEX_TTL)
    now = time.time()
    if _INDEX_CACHE is not None and (now - _INDEX_CACHE.built_at) < ttl:
        return _INDEX_CACHE

    index = _build_product_index(debug=debug)
    _INDEX_CACHE = index
    return index


def _rank_to_match(
    ranked: RankedMatch,
    metadata: List[ProductDocument],
) -> ProductMatch:
    doc = metadata[ranked.index]
    return ProductMatch(
        label=doc.label,
        purchase_url=doc.purchase_url,
        product=doc.product,
        sku=doc.sku,
        tfidf_score=ranked.tfidf_score,
        lexical_score=ranked.lexical_score,
        forced=ranked.forced,
    )


def search_products_hybrid(
    query: str,
    *,
    top_k: int = 3,
    debug: bool = False,
) -> ProductSearchResult:
    normalized_query = normalize_basic(query)
    if not normalized_query:
        return ProductSearchResult(matches=[], confidence="none", error="empty_query")

    try:
        index = get_or_build_product_index(debug=debug)
    except ProductIndexUnavailable as exc:
        return ProductSearchResult(matches=[], confidence="none", error=str(exc))

    ranked = index.ranker.search(normalized_query, top_k=top_k)
    if not ranked:
        return ProductSearchResult(matches=[], confidence="none", error=None)

    matches = [_rank_to_match(item, index.metadata) for item in ranked]
    top_match = matches[0]

    confidence = "low"
    if top_match.tfidf_score >= _HIGH_CONF_THRESHOLD or (
        top_match.lexical_score is not None
        and top_match.lexical_score >= _FUZZY_ACCEPT_THRESHOLD
    ):
        confidence = "high"
    elif top_match.tfidf_score >= _MEDIUM_CONF_THRESHOLD or (
        top_match.lexical_score is not None
        and top_match.lexical_score >= _FUZZY_MIN_THRESHOLD
    ):
        confidence = "medium"
    else:
        confidence = "low"

    if debug:
        print(
            f"[DEBUG] Busca produto '{query}' normalizada='{normalized_query}', "
            f"melhor_score={top_match.tfidf_score:.3f}, "
            f"lexical={top_match.lexical_score}"
        )

    return ProductSearchResult(matches=matches, confidence=confidence, error=None)
