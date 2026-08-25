import os
import re
from collections.abc import Callable
from typing import Any

import httpx
from dotenv import load_dotenv
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from pydantic_models.mapping_types import IDENTITY_PRODUCT_MAPPING
from pydantic_models.product_types import AgentProduct
from services.connectors.sql_connector import SqlConnector
from services.ingest_service import save_ai_mapping, sync_vendor
from services.mapping_loader import load_vendor_config
from services.normalization_service import normalize_product

load_dotenv()

TARGET_FIELDS = ("id", "title", "price", "description", "categories")
PREFERRED_TABLES = (
    "products",
    "product",
    "inventory",
    "catalog",
    "items",
    "item",
    "listings",
    "sku",
    "skus",
)
MAX_ATTEMPTS = 4  # initial try + 3 retries
LLMComplete = Callable[[str], str]


def extract_schema(engine: Engine) -> dict[str, Any]:
    inspector = inspect(engine)
    table_names = list(inspector.get_table_names())
    if not table_names:
        raise ValueError("Vendor database has no tables to map")

    table = _choose_inventory_table(table_names, inspector)
    columns = []
    for column in inspector.get_columns(table):
        columns.append(
            {
                "name": column["name"],
                "type": str(column.get("type", "")),
            }
        )
    if not columns:
        raise ValueError(f"Selected table '{table}' has no columns")
    return {"table": table, "tables": table_names, "columns": columns}


def generate_mapping_query(
    schema: dict[str, Any],
    error_feedback: str | None = None,
    llm_complete: LLMComplete | None = None,
) -> str:
    prompt = _build_prompt(schema, error_feedback)
    complete = llm_complete or llm_complete_default
    raw = complete(prompt)
    return _extract_sql(raw)


def validate_and_save_mapping(
    vendor_id: int,
    encrypted_url: str,
    schema: dict[str, Any] | None = None,
    llm_complete: LLMComplete | None = None,
    auto_sync: bool = True,
) -> dict[str, Any]:
    engine = SqlConnector.engine_from_encrypted_url(encrypted_url)
    try:
        schema = schema or extract_schema(engine)
    finally:
        engine.dispose()

    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        query = generate_mapping_query(schema, last_error, llm_complete=llm_complete)
        try:
            rows = SqlConnector.preview_query(encrypted_url, query, limit=5)
            if not rows:
                raise ValueError("AI query returned no sample rows")

            valid_products = []
            failures = []
            for index, row in enumerate(rows):
                try:
                    product = normalize_product(row, IDENTITY_PRODUCT_MAPPING)
                    if product is None:
                        raise ValueError(
                            "Row failed AgentProduct completeness checks "
                            "(id, title, price_in_cents > 0, description required)"
                        )
                    AgentProduct.model_validate(product.model_dump())
                    valid_products.append(product)
                except Exception as exc:
                    failures.append(f"row {index}: {exc}; keys={list(row.keys())}")

            if not valid_products:
                raise ValueError(
                    "No sample rows produced a valid AgentProduct. " + "; ".join(failures)
                )

            save_ai_mapping(
                vendor_id,
                query=query,
                table=schema["table"],
                encrypted_url=encrypted_url,
                id_column=_alias_source_column(query, "id") or _infer_id_column(schema),
                stock_column=_alias_source_column(query, "stock") or _infer_stock_column(schema),
            )
            result = {
                "vendor_id": vendor_id,
                "table": schema["table"],
                "query": query,
                "attempts": attempt,
                "sample_valid": len(valid_products),
                "sample_rows": len(rows),
            }
            if auto_sync:
                result["sync"] = sync_vendor(vendor_id)
            return result
        except Exception as exc:
            last_error = str(exc)

    raise ValueError(
        f"AI schema mapping failed after {MAX_ATTEMPTS} attempts. Last error: {last_error}"
    )


def onboard_vendor_sql(
    vendor_id: int,
    llm_complete: LLMComplete | None = None,
) -> dict[str, Any]:
    config = load_vendor_config(vendor_id)
    if config.sql is None or not config.sql.encrypted_url:
        raise ValueError(f"Vendor {vendor_id} has no encrypted database URL")
    return validate_and_save_mapping(
        vendor_id,
        encrypted_url=config.sql.encrypted_url,
        llm_complete=llm_complete,
        auto_sync=True,
    )


def llm_complete_default(prompt: str) -> str:
    openai_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY")
    if openai_key:
        return _complete_openai(prompt, openai_key)
    if google_key:
        return _complete_google(prompt, google_key)
    raise RuntimeError(
        "No LLM API key configured. Set OPENAI_API_KEY (or LLM_API_KEY) "
        "or GOOGLE_API_KEY in .env"
    )


def _choose_inventory_table(table_names: list[str], inspector) -> str:
    lowered = {name.lower(): name for name in table_names}
    for preferred in PREFERRED_TABLES:
        if preferred in lowered:
            return lowered[preferred]
    for preferred in PREFERRED_TABLES:
        for original in table_names:
            if preferred in original.lower():
                return original

    best_name = table_names[0]
    best_score = -1
    keywords = {"id", "sku", "title", "name", "price", "description", "category", "product"}
    for name in table_names:
        column_names = {col["name"].lower() for col in inspector.get_columns(name)}
        score = len(keywords & column_names)
        if score > best_score:
            best_score = score
            best_name = name
    return best_name


def _build_prompt(schema: dict[str, Any], error_feedback: str | None) -> str:
    column_lines = "\n".join(
        f"- {col['name']} ({col['type']})" for col in schema["columns"]
    )
    feedback = ""
    if error_feedback:
        feedback = (
            "\nThe previous SQL failed validation. Fix it.\n"
            f"Error:\n{error_feedback}\n"
        )
    return f"""You are a strict data engineer. Map a vendor inventory table to AgentProduct.

Target aliases (exact names required):
- id (string product identifier)
- title (product name)
- price (numeric sale price in vendor currency, dollars not cents)
- description (non-empty product text)
- categories (category name or list-like text)
- stock (numeric on-hand quantity; use 0 if unknown)

Vendor table: {schema["table"]}
Vendor columns:
{column_lines}

Rules:
- Return ONLY one SQL SELECT statement. No markdown, no comments, no explanation.
- Use AS aliases to the target names above.
- FROM must be the vendor table `{schema["table"]}`.
- Read-only SELECT only. Never INSERT/UPDATE/DELETE/DDL.
- Do not wrap the query in LIMIT; the caller adds LIMIT for sampling.
{feedback}"""


def _extract_sql(raw: str) -> str:
    text = raw.strip()
    fenced = re.search(r"```(?:sql)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    return text.rstrip(";")


def _alias_source_column(query: str, alias: str) -> str | None:
    pattern = rf'(["`\[]?)([A-Za-z_][A-Za-z0-9_]*)\1\s+AS\s+(["`\[]?){re.escape(alias)}\3\b'
    match = re.search(pattern, query, re.IGNORECASE)
    if match:
        return match.group(2)
    return None


def _infer_stock_column(schema: dict[str, Any]) -> str | None:
    hints = (
        "stock_quantity",
        "stock",
        "quantity",
        "qty",
        "inventory",
        "units",
        "available",
        "availability",
    )
    names = [col["name"] for col in schema.get("columns", [])]
    lowered = {name.lower(): name for name in names}
    for hint in hints:
        if hint in lowered:
            return lowered[hint]
    for name in names:
        if any(hint in name.lower() for hint in ("stock", "qty", "quantity")):
            return name
    return None


def _infer_id_column(schema: dict[str, Any]) -> str | None:
    names = [col["name"] for col in schema.get("columns", [])]
    lowered = {name.lower(): name for name in names}
    for hint in ("product_id", "sku", "id", "item_id"):
        if hint in lowered:
            return lowered[hint]
    return names[0] if names else None


def _complete_openai(prompt: str, api_key: str) -> str:
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
    response = httpx.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "Return only SQL. No markdown."},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=60.0,
    )
    response.raise_for_status()
    payload = response.json()
    return payload["choices"][0]["message"]["content"]


def _complete_google(prompt: str, api_key: str) -> str:
    model = os.getenv("GOOGLE_MODEL") or os.getenv("LLM_MODEL") or "gemini-2.0-flash"
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    response = httpx.post(
        url,
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0},
        },
        timeout=60.0,
    )
    response.raise_for_status()
    payload = response.json()
    return payload["candidates"][0]["content"]["parts"][0]["text"]
