from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests

CATALOG_URL = "https://api.dooki.com.br/v2/vz-store5/catalog/products?include=skus"
DEFAULT_TIMEOUT = 10

_session: Optional[requests.Session] = None


@dataclass
class Timestamp:
    date: str
    timezone_type: int
    timezone: str

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["Timestamp"]:
        if not data:
            return None
        try:
            date = str(data.get("date"))
            timezone_type = int(data.get("timezone_type", 0))
            timezone = str(data.get("timezone", ""))
        except (TypeError, ValueError):
            return None
        if not date:
            return None
        return cls(date=date, timezone_type=timezone_type, timezone=timezone)


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
    created_at: Optional[Timestamp]
    updated_at: Optional[Timestamp]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Sku":
        def _float(value: Any) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        return cls(
            id=int(data.get("id", 0)),
            product_id=int(data.get("product_id", 0)),
            sku=str(data.get("sku", "")),
            token=_safe_str(data.get("token")),
            title=str(data.get("title", "")),
            availability=int(data.get("availability", 0)),
            price_sale=_float(data.get("price_sale")),
            price_discount=_float(data.get("price_discount")),
            purchase_url=_safe_str(data.get("purchase_url")),
            created_at=Timestamp.from_dict(_ensure_dict(data.get("created_at"))),
            updated_at=Timestamp.from_dict(_ensure_dict(data.get("updated_at"))),
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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Product":
        skus_data: List[Dict[str, Any]] = []
        raw_skus = data.get("skus")
        if isinstance(raw_skus, dict):
            skus_data = raw_skus.get("data") or []
        elif isinstance(raw_skus, list):
            skus_data = raw_skus

        parsed_skus: List[Sku] = []
        for item in skus_data:
            if isinstance(item, dict):
                parsed_skus.append(Sku.from_dict(item))

        return cls(
            id=int(data.get("id", 0)),
            name=str(data.get("name", "")),
            slug=str(data.get("slug", "")),
            sku=_safe_str(data.get("sku")),
            url=_safe_str(data.get("url")),
            preview_url=_safe_str(data.get("preview_url")),
            skus=parsed_skus,
        )

    def matches(self, needle: str) -> bool:
        candidates = [self.name, self.slug]
        for value in candidates:
            if value and needle in value.casefold():
                return True
        for sku in self.skus:
            if sku.title and needle in sku.title.casefold():
                return True
        return False


__all__ = [
    "fetch_products",
    "search_products",
    "get_purchase_url_for",
    "get_session",
    "Product",
    "Sku",
    "Timestamp",
]


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _ensure_dict(value: Any) -> Optional[Dict[str, Any]]:
    return value if isinstance(value, dict) else None


def get_session() -> requests.Session:
    global _session
    if _session is not None:
        return _session

    token = os.environ.get("YAMPI_USER_TOKEN")
    secret = os.environ.get("YAMPI_USER_SECRET_KEY")
    missing = [name for name, val in (
        ("YAMPI_USER_TOKEN", token),
        ("YAMPI_USER_SECRET_KEY", secret),
    ) if not val]
    if missing:
        raise RuntimeError(
            "Variaveis de ambiente ausentes: " + ", ".join(missing)
        )

    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "User-Token": token,
            "User-Secret-Key": secret,
        }
    )
    _session = session
    return session


def _parse_products(payload: Any) -> List[Product]:
    products: List[Product] = []
    if isinstance(payload, dict):
        items = payload.get("data")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    products.append(Product.from_dict(item))
    return products


def _extract_next_page(payload: Any, current_page: int) -> Optional[int]:
    if not isinstance(payload, dict):
        return None
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return None
    pagination = meta.get("pagination")
    if not isinstance(pagination, dict):
        return None

    current = pagination.get("current_page")
    total = pagination.get("total_pages")
    if isinstance(current, int) and isinstance(total, int):
        if current < total:
            next_page = current + 1
            if next_page != current_page:
                return next_page
        else:
            return None

    links = pagination.get("links")
    if isinstance(links, dict):
        next_link = links.get("next")
        if isinstance(next_link, str) and next_link:
            parsed = urlparse(next_link)
            params = parse_qs(parsed.query)
            page_values = params.get("page")
            if page_values:
                try:
                    page_number = int(page_values[0])
                except (TypeError, ValueError):
                    return None
                if page_number != current_page:
                    return page_number
    return None


def _fetch_catalog_page(session: requests.Session, page: int) -> Tuple[List[Product], Optional[int]]:
    params = {"page": page} if page and page > 0 else None
    response = session.get(CATALOG_URL, params=params, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    products = _parse_products(payload)
    next_page = _extract_next_page(payload, page)
    return products, next_page


def _iter_catalog_products() -> Iterator[Product]:
    session = get_session()
    page = 1
    while True:
        products, next_page = _fetch_catalog_page(session, page)
        for product in products:
            yield product
        if not next_page or next_page == page:
            break
        page = next_page


def _iter_matching_products(needle: str) -> Iterator[Product]:
    for product in _iter_catalog_products():
        if product.matches(needle):
            yield product


def fetch_products() -> List[Product]:
    return list(_iter_catalog_products())


def search_products(query: str) -> List[Product]:
    needle = query.casefold().strip()
    if not needle:
        return []
    return list(_iter_matching_products(needle))


def get_purchase_url_for(query: str) -> Optional[str]:
    needle = query.casefold().strip()
    if not needle:
        return None
    for product in _iter_matching_products(needle):
        for sku in product.skus:
            if sku.purchase_url:
                return sku.purchase_url
    return None


def _cli(argv: List[str]) -> int:
    if len(argv) != 2:
        print("Uso: python -m product_lookup \"<texto de busca>\"", file=sys.stderr)
        return 1
    query = argv[1].strip()
    if not query:
        print("Informe um termo de busca nao vazio.", file=sys.stderr)
        return 1
    try:
        url = get_purchase_url_for(query)
    except RuntimeError as exc:
        print(f"Erro de configuracao: {exc}", file=sys.stderr)
        return 2
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
