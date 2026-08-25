from functools import lru_cache

import yaml

from pydantic_models.mapping_types import ProductFieldMapping, SqlSourceConfig, VendorConfig
from services.vendor_registry import CONFIG_ROOT


def _parse_vendor_config(payload: dict) -> VendorConfig:
    fields = payload.get("mapping") or {}
    mapping_fields = {
        key: value
        for key, value in fields.items()
        if key in {"id", "title", "price", "description", "categories"}
    }
    source = payload.get("source") or fields.get("source")
    mapping = None
    if mapping_fields:
        mapping = ProductFieldMapping(source=source, **mapping_fields)
    sql = SqlSourceConfig(**payload["sql"]) if payload.get("sql") else None
    return VendorConfig(source=source, mapping=mapping, sql=sql)


@lru_cache
def _load_vendor_config(vendor_key: str) -> VendorConfig:
    path = CONFIG_ROOT / vendor_key / "mapping.yaml"
    if not path.is_file():
        raise FileNotFoundError(
            f"No vendor configuration for {vendor_key}. Expected {path}"
        )

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _parse_vendor_config(payload)


def load_vendor_config(vendor_key: str | int) -> VendorConfig:
    return _load_vendor_config(str(vendor_key))


def load_product_mapping(vendor_key: str | int) -> ProductFieldMapping:
    mapping = load_vendor_config(vendor_key).mapping
    if mapping is None:
        raise ValueError(
            f"Vendor {vendor_key} has no field mapping yet. Run SQL onboarding first."
        )
    return mapping


def clear_mapping_cache() -> None:
    _load_vendor_config.cache_clear()
