import re
from pathlib import Path

from pydantic_models.mapping_types import ProductFieldMapping
from pydantic_models.product_types import AgentProduct
from services.mapping_loader import load_product_mapping

_TYPOGRAPHIC_REPLACEMENTS = str.maketrans({
    "\u2018": "'",  # ‘
    "\u2019": "'",  # ’
    "\u201c": '"',  # “
    "\u201d": '"',  # ”
    "\u2013": "-",  # –
    "\u2014": "-",  # —
})


def clean_text(raw_text: str) -> str:
    if raw_text is None or not isinstance(raw_text, str):
        return ""
    text = raw_text.translate(_TYPOGRAPHIC_REPLACEMENTS)
    text = text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text).strip()


def _price_to_cents(price) -> int:
    if price is None:
        return 0
    if isinstance(price, bool):
        return 0
    if isinstance(price, (int, float)):
        if isinstance(price, float) and price != price:  # NaN
            return 0
        return max(int(round(float(price) * 100)), 0)
    if isinstance(price, str):
        cleaned = price.strip().replace("$", "").replace(",", "")
        if not cleaned:
            return 0
        try:
            return max(int(round(float(cleaned) * 100)), 0)
        except ValueError:
            return 0
    return 0


def _as_string_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _flatten_description(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return " ".join(str(part).strip() for part in value if str(part).strip())
    return str(value).strip()


def _is_missing_text(value) -> bool:
    if value is None:
        return True
    return not str(value).strip()


def _source_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def normalize_product(raw_item: dict, mapping: ProductFieldMapping) -> AgentProduct | None:
    product_id = raw_item.get(mapping.id)
    title = clean_text(_source_text(raw_item.get(mapping.title)) or "")
    if _is_missing_text(product_id) or _is_missing_text(title):
        return None

    if mapping.price not in raw_item or raw_item.get(mapping.price) is None:
        return None
    price_in_cents = _price_to_cents(raw_item.get(mapping.price))
    if price_in_cents == 0:
        return None

    description = clean_text(_flatten_description(raw_item.get(mapping.description)))
    if not description:
        return None

    categories_raw = raw_item.get(mapping.categories) if mapping.categories else None
    return AgentProduct(
        id=str(product_id).strip(),
        title=title,
        price_in_cents=price_in_cents,
        categories=_as_string_list(categories_raw),
        description=description,
    )


def normalize_amazon_product(raw_item: dict) -> AgentProduct | None:
    return normalize_product(raw_item, load_product_mapping("amazon"))


class normalization_service:
    def __init__(self, vendor_id: int, database_path: Path | None = None):
        self.vendor_id = vendor_id
        self.database_path = database_path or Path(__file__).resolve().parents[1] / "database"

    def run(self) -> bool:
        from services.ingest_service import sync_vendor

        sync_vendor(self.vendor_id)
        return True
