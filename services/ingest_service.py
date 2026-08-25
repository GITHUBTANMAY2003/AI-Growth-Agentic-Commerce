import json
from pathlib import Path

import yaml

from pydantic_models.mapping_types import IDENTITY_PRODUCT_MAPPING
from pydantic_models.request_types import SqlSourceRequest
from services.connectors.sql_connector import SqlConnector
from services.mapping_loader import clear_mapping_cache, load_product_mapping, load_vendor_config
from services.normalization_service import normalize_product
from services.security import encrypt_credential
from services.vendor_registry import vendor_catalog_json, vendor_config_dir


def _mapping_yaml_path(vendor_id: int) -> Path:
    return vendor_config_dir(vendor_id) / "mapping.yaml"


def _read_mapping_yaml(vendor_id: int) -> dict:
    path = _mapping_yaml_path(vendor_id)
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _write_mapping_yaml(vendor_id: int, payload: dict) -> Path:
    path = _mapping_yaml_path(vendor_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    clear_mapping_cache()
    return path


def save_sql_source(vendor_id: int, request: SqlSourceRequest) -> Path:
    existing = _read_mapping_yaml(vendor_id)
    sql_block = {"encrypted_url": encrypt_credential(request.database_url)}
    if existing.get("sql", {}).get("query"):
        sql_block["query"] = existing["sql"]["query"]
    if existing.get("sql", {}).get("table"):
        sql_block["table"] = existing["sql"]["table"]
    if existing.get("sql", {}).get("id_column"):
        sql_block["id_column"] = existing["sql"]["id_column"]
    if existing.get("sql", {}).get("stock_column"):
        sql_block["stock_column"] = existing["sql"]["stock_column"]
    payload = {
        "source": "sql",
        "sql": sql_block,
    }
    if existing.get("mapping"):
        payload["mapping"] = existing["mapping"]
    return _write_mapping_yaml(vendor_id, payload)


def save_ai_mapping(
    vendor_id: int,
    query: str,
    table: str,
    encrypted_url: str,
    id_column: str | None = None,
    stock_column: str | None = None,
) -> Path:
    sql_block = {
        "encrypted_url": encrypted_url,
        "query": query,
        "table": table,
    }
    if id_column:
        sql_block["id_column"] = id_column
    if stock_column:
        sql_block["stock_column"] = stock_column
    payload = {
        "source": "sql",
        "mapping": IDENTITY_PRODUCT_MAPPING.model_dump(exclude={"source"}, exclude_none=True),
        "sql": sql_block,
    }
    return _write_mapping_yaml(vendor_id, payload)


def _build_sql_connector(vendor_id: int, config):
    if config.sql is None:
        raise ValueError(
            f"Vendor {vendor_id} source is sql but mapping.yaml has no sql block"
        )
    if not config.sql.query:
        raise ValueError(
            f"Vendor {vendor_id} has no AI-generated SQL query yet. Run SQL onboarding."
        )
    return SqlConnector(
        encrypted_url=config.sql.encrypted_url,
        query=config.sql.query,
        table=config.sql.table,
    )


# Only SQL is implemented today. New engines plug in here without changing sync_vendor.
_CONNECTOR_BUILDERS = {
    "sql": _build_sql_connector,
}


def _connector_for_vendor(vendor_id: int):
    config = load_vendor_config(vendor_id)
    source = (config.source or "sql").lower()
    if source == "amazon":
        raise ValueError("Amazon catalogs are synced with main_sync.py, not /vendors/{id}/sync")
    builder = _CONNECTOR_BUILDERS.get(source)
    if builder is None:
        supported = ", ".join(sorted(_CONNECTOR_BUILDERS))
        raise ValueError(
            f"Unsupported vendor source '{source}' for vendor {vendor_id}. "
            f"Implemented sources: {supported}. "
            "Add a CatalogConnector implementation and register it in _CONNECTOR_BUILDERS."
        )
    return builder(vendor_id, config), source


def sync_vendor(vendor_id: int) -> dict:
    mapping = load_product_mapping(vendor_id)
    connector, source = _connector_for_vendor(vendor_id)
    destination = vendor_catalog_json(vendor_id)
    destination.parent.mkdir(parents=True, exist_ok=True)

    products: list[dict] = []
    dropped = 0
    for raw_item in connector.stream_products():
        product = normalize_product(raw_item, mapping)
        if product is None:
            dropped += 1
            continue
        products.append(product.model_dump())

    with destination.open("w", encoding="utf-8") as handle:
        json.dump(products, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return {
        "vendor_id": vendor_id,
        "source": source,
        "output": str(destination),
        "written": len(products),
        "dropped": dropped,
    }


def load_normalized_catalog(vendor_id: int) -> list[dict]:
    path = vendor_catalog_json(vendor_id)
    if not path.is_file():
        raise FileNotFoundError(f"Normalized catalog not found for vendor {vendor_id}")
    return json.loads(path.read_text(encoding="utf-8"))
