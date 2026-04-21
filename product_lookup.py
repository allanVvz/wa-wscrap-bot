from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple

import bs4 as _bs4
import requests

STORE_URL = "https://www.vzforeal.com"
CATALOG_URL = f"{STORE_URL}/products.json"
DEFAULT_TIMEOUT = 10
_PAGE_LIMIT = 250

_session: Optional[requests.Session] = None


@dataclass
class Sku:
    id: int
    product_id: int
    sku: str
    token: Optional[str]
    title: str
    availability: int
    price_sale: float
    price_discount: float
    purchase_url: Optional[str]

    @classmethod
    def from_variant(cls, data: Dict[str, Any], product_handle: str) -> "Sku":
        def _float(v: Any) -> float:
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0.0

        variant_id = int(data.get("id", 0))
        available = bool(data.get("available", False))
        url = f"{STORE_URL}/products/{product_handle}?variant={variant_id}" if product_handle else None

        return cls(
            id=variant_id,
            product_id=int(data.get("product_id", 0)),
            sku=str(data.get("sku") or ""),
            token=None,
            title=str(data.get("title") or ""),
            availability=1 if available else 0,
            price_sale=_float(data.get("price")),
            price_discount=_float(data.get("compare_at_price")),
            purchase_url=url,
        )


@dataclass
class Product:
    id: int
    name: str
    slug: str
    sku: Optional[str]
    url: Optional[str]
    preview_url: Optional[str]
    skus: List[Sku]
    tags: List[str] = field(default_factory=list)
    product_type: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Product":
        handle = str(data.get("handle") or "")
        product_url = f"{STORE_URL}/products/{handle}" if handle else None

        variants_raw = data.get("variants") or []
        skus = [Sku.from_variant(v, handle) for v in variants_raw if isinstance(v, dict)]

        images = data.get("images") or []
        preview_url = None
        if images and isinstance(images[0], dict):
            preview_url = images[0].get("src")

        raw_tags = data.get("tags") or []
        if isinstance(raw_tags, str):
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        elif isinstance(raw_tags, list):
            tags = [str(t).strip() for t in raw_tags if t]
        else:
            tags = []

        return cls(
            id=int(data.get("id", 0)),
            name=str(data.get("title") or ""),
            slug=handle,
            sku=None,
            url=product_url,
            preview_url=preview_url,
            skus=skus,
            tags=tags,
            product_type=str(data.get("product_type") or ""),
        )

    def matches(self, needle: str) -> bool:
        for value in (self.name, self.slug):
            if value and needle in value.casefold():
                return True
        for sku in self.skus:
            if sku.title and needle in sku.title.casefold():
                return True
        return False


__all__ = ["fetch_products", "search_products", "get_purchase_url_for", "get_session", "get_product_description", "Product", "Sku"]


def get_session() -> requests.Session:
    global _session
    if _session is not None:
        return _session
    session = requests.Session()
    session.headers.update({"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
    _session = session
    return session


def _parse_products(payload: Any) -> List[Product]:
    if not isinstance(payload, dict):
        return []
    return [Product.from_dict(item) for item in (payload.get("products") or []) if isinstance(item, dict)]


def _fetch_catalog_page(session: requests.Session, page: int) -> Tuple[List[Product], Optional[int]]:
    response = session.get(CATALOG_URL, params={"limit": _PAGE_LIMIT, "page": page}, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    products = _parse_products(response.json())
    next_page = page + 1 if len(products) == _PAGE_LIMIT else None
    return products, next_page


def _iter_catalog_products() -> Iterator[Product]:
    session = get_session()
    page = 1
    while True:
        products, next_page = _fetch_catalog_page(session, page)
        for product in products:
            yield product
        if not next_page:
            break
        page = next_page


def fetch_products() -> List[Product]:
    return list(_iter_catalog_products())


def search_products(query: str) -> List[Product]:
    needle = query.casefold().strip()
    if not needle:
        return []
    return [p for p in _iter_catalog_products() if p.matches(needle)]


def get_purchase_url_for(query: str) -> Optional[str]:
    needle = query.casefold().strip()
    if not needle:
        return None
    for product in _iter_catalog_products():
        if product.matches(needle):
            for sku in product.skus:
                if sku.purchase_url:
                    return sku.purchase_url
    return None


_PROMO_TAGS = {
    "promocao", "promoção", "promo", "destaque", "oferta", "sale",
    "compre-1-leve-2", "compre-um-leve-dois", "buy-1-get-1", "leve-2",
}


def is_featured_product(product: "Product") -> bool:
    """Returns True if the product is on discount or has a promo tag."""
    for sku in product.skus:
        if sku.price_discount and sku.price_discount > sku.price_sale > 0:
            return True
    product_tags = {t.lower().strip().replace(" ", "-") for t in product.tags}
    return bool(product_tags & _PROMO_TAGS)


def get_product_description(product_url: str, timeout: int = 8) -> Optional[str]:
    """Fetches and returns a brief product description scraped from the store page."""
    try:
        session = get_session()
        resp = session.get(product_url, timeout=timeout)
        resp.raise_for_status()
        soup = _bs4.BeautifulSoup(resp.content, "lxml")

        _DESC_SELECTORS = [
            {"class": re.compile(r"product-description|product__description|product-single__description")},
            {"itemprop": "description"},
            {"class": re.compile(r"rte|product__info-description")},
        ]
        desc_elem = None
        for attrs in _DESC_SELECTORS:
            desc_elem = soup.find("div", attrs)
            if desc_elem:
                break

        if not desc_elem:
            return None

        text = desc_elem.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return None
        if len(text) > 280:
            text = text[:280].rsplit(" ", 1)[0] + "..."
        return text
    except Exception:
        return None


def _cli(argv: List[str]) -> int:
    if len(argv) != 2:
        print("Uso: python product_lookup.py \"<texto de busca>\"", file=sys.stderr)
        return 1
    query = argv[1].strip()
    if not query:
        print("Informe um termo de busca nao vazio.", file=sys.stderr)
        return 1
    try:
        url = get_purchase_url_for(query)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "HTTP"
        print(f"Erro HTTP ({status}): {exc}", file=sys.stderr)
        return 3
    except requests.RequestException as exc:
        print(f"Erro de rede ao consultar catalogo: {exc}", file=sys.stderr)
        return 4

    if url:
        print(url)
        return 0
    print(f"Nenhum resultado para: {query}")
    return 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
