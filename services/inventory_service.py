import re
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.pool import NullPool

from services.mapping_loader import load_vendor_config
from services.security import decrypt_credential

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _get_ephemeral_engine(db_url: str) -> Engine:
    url = make_url(db_url)
    connect_args: dict = {}
    render_url = db_url
    if url.get_backend_name() == "sqlite":
        database = url.database
        if database and database != ":memory:":
            db_path = Path(database).expanduser().resolve()
            render_url = f"sqlite:///file:{db_path.as_posix()}?mode=ro&uri=true"
            connect_args["uri"] = True
    return create_engine(
        render_url,
        poolclass=NullPool,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def _quote_ident(name: str) -> str:
    if not name or not _IDENT.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return f'"{name}"'


def verify_in_stock(vendor_id: int, product_id: str) -> bool:
    if not product_id or not str(product_id).strip():
        raise ValueError("product_id is required")

    config = load_vendor_config(vendor_id)
    if config.sql is None or not config.sql.encrypted_url:
        raise ValueError(f"Vendor {vendor_id} has no encrypted database URL")

    table = config.sql.table
    stock_column = config.sql.stock_column
    id_column = config.sql.id_column
    if config.mapping and not id_column:
        mapped_id = config.mapping.id
        if mapped_id and mapped_id != "id":
            id_column = mapped_id
    if not table or not stock_column or not id_column:
        raise ValueError(
            f"Vendor {vendor_id} is missing JIT stock mapping "
            "(sql.table, sql.id_column, sql.stock_column). Re-run SQL onboarding."
        )

    db_url = decrypt_credential(config.sql.encrypted_url)
    statement = text(
        f"SELECT {_quote_ident(stock_column)} FROM {_quote_ident(table)} "
        f"WHERE {_quote_ident(id_column)} = :product_id"
    )

    engine = _get_ephemeral_engine(db_url)
    try:
        with engine.connect() as conn:
            row = conn.execute(statement, {"product_id": str(product_id).strip()}).first()
            if row is None or row[0] is None:
                return False
            try:
                return float(row[0]) > 0
            except (TypeError, ValueError):
                return False
    finally:
        engine.dispose()
