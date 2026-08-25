"""Onboard mock_vendor.db: encrypt URL, map scrambled columns, full-overwrite sync."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic_models.request_types import SqlSourceRequest
from services.ai_schema_mapper import onboard_vendor_sql
from services.ingest_service import save_sql_source, sync_vendor
from services.vendor_registry import MOCK_VENDOR_DB, MOCK_VENDOR_TABLE, mock_vendor_sqlite_url, register_vendor

MOCK_MAPPING_SQL = f"""
SELECT
    vendor_sku AS id,
    vendor_item_name AS title,
    cost AS price,
    long_blurb AS description,
    dept_path AS categories,
    stock_qty AS stock
FROM {MOCK_VENDOR_TABLE}
""".strip()


def fixture_llm_for_mock_vendor(prompt: str) -> str:
    """Stand-in for the LLM when testing the known mock schema without an API key."""
    return MOCK_MAPPING_SQL


def main() -> None:
    parser = argparse.ArgumentParser(description="Onboard sqlite mock vendor and sync snapshot")
    parser.add_argument("--vendor-id", type=int, default=None)
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Call the real LLM instead of the fixture mapper for this mock schema",
    )
    args = parser.parse_args()

    if not MOCK_VENDOR_DB.is_file():
        raise FileNotFoundError(
            f"{MOCK_VENDOR_DB} not found. Run: python scripts/setup_mock_vendor.py"
        )

    vendor_id = args.vendor_id
    if vendor_id is None:
        created = register_vendor("Mock SQLite Vendor")
        vendor_id = created["vendor_id"]
        print(f"Registered vendor_id={vendor_id}")

    sqlite_url = mock_vendor_sqlite_url()
    save_sql_source(vendor_id, SqlSourceRequest(database_url=sqlite_url))
    llm = None if args.use_llm else fixture_llm_for_mock_vendor
    onboard = onboard_vendor_sql(vendor_id, llm_complete=llm)
    print("AI mapping query:\n", onboard["query"])
    print("Onboard result:", {k: onboard[k] for k in ("table", "attempts", "sample_valid") if k in onboard})
    if "sync" in onboard:
        print("Sync:", onboard["sync"])
    else:
        print("Sync:", sync_vendor(vendor_id))


if __name__ == "__main__":
    main()
