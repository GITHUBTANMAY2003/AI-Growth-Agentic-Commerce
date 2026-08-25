"""Build a messy vendor SQLite catalog from canonical Amazon AgentProduct JSON."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_JSON = ROOT / "database" / "amazon" / "products.json"
DB_PATH = ROOT / "mock_vendor.db"
VENDOR_TABLE = "vendor_catalog"


def load_canonical_products() -> list[dict]:
    if not SOURCE_JSON.is_file():
        raise FileNotFoundError(
            f"Canonical catalog missing: {SOURCE_JSON}. Run main_sync.py first."
        )
    products = json.loads(SOURCE_JSON.read_text(encoding="utf-8"))
    if not isinstance(products, list) or not products:
        raise ValueError(f"{SOURCE_JSON} did not contain a product list")
    return products


def to_vendor_row(product: dict) -> tuple:
    categories = product.get("categories") or []
    if isinstance(categories, list):
        dept_path = " > ".join(str(part) for part in categories if str(part).strip())
    else:
        dept_path = str(categories)
    cents = int(product.get("price_in_cents") or 0)
    return (
        str(product["id"]),
        str(product.get("title") or ""),
        cents / 100.0,
        dept_path,
        str(product.get("description") or ""),
        10,
    )


def reset_schema(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS vendor_catalog")
    conn.execute("DROP TABLE IF EXISTS staff_users")
    conn.execute(
        """
        CREATE TABLE staff_users (
            user_id INTEGER PRIMARY KEY,
            email TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE vendor_catalog (
            vendor_sku TEXT PRIMARY KEY,
            vendor_item_name TEXT NOT NULL,
            cost REAL NOT NULL,
            dept_path TEXT,
            long_blurb TEXT,
            stock_qty INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute("INSERT INTO staff_users (email) VALUES ('ops@vendor.example')")


def insert_rows(conn: sqlite3.Connection, products: list[dict]) -> int:
    rows = [to_vendor_row(product) for product in products]
    conn.executemany(
        """
        INSERT INTO vendor_catalog (
            vendor_sku,
            vendor_item_name,
            cost,
            dept_path,
            long_blurb,
            stock_qty
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def main() -> None:
    products = load_canonical_products()
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    try:
        reset_schema(conn)
        count = insert_rows(conn, products)
        conn.commit()
    finally:
        conn.close()
    print(f"Wrote {count} rows to {DB_PATH} table {VENDOR_TABLE}")


if __name__ == "__main__":
    main()
