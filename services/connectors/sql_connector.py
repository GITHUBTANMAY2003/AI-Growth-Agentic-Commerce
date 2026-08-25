import re
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.pool import NullPool

from services.security import decrypt_credential

_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")
_FORBIDDEN_SQL = (
    " insert ",
    " update ",
    " delete ",
    " drop ",
    " alter ",
    " create ",
    " truncate ",
    " grant ",
    " revoke ",
    " copy ",
    " replace ",
    " merge ",
    " call ",
    " execute ",
    " into ",
)


class SqlConnector:
    def __init__(
        self,
        encrypted_url: str,
        query: str | None = None,
        table: str | None = None,
    ):
        if not query and not table:
            raise ValueError("SqlConnector requires a SQL query or a table name")

        plaintext_url = decrypt_credential(encrypted_url)
        self._statement = text(self._read_only_sql(query=query, table=table))
        self._engine = self._create_read_only_engine(plaintext_url)

    @classmethod
    def engine_from_encrypted_url(cls, encrypted_url: str) -> Engine:
        return cls._create_read_only_engine(decrypt_credential(encrypted_url))

    def stream_products(self) -> Iterator[dict]:
        try:
            with self._engine.connect() as conn:
                with conn.begin():
                    self._apply_read_only(conn)
                    result = conn.execution_options(stream_results=True).execute(self._statement)
                    for row in result.mappings():
                        yield {key: self._json_safe(value) for key, value in dict(row).items()}
        finally:
            self._engine.dispose()

    @classmethod
    def preview_query(cls, encrypted_url: str, query: str, limit: int = 5) -> list[dict]:
        sql = cls._read_only_sql(query=query, table=None)
        if " limit " not in f" {sql.lower()} ":
            sql = f"{sql} LIMIT {int(limit)}"
        engine = cls.engine_from_encrypted_url(encrypted_url)
        try:
            with engine.connect() as conn:
                with conn.begin():
                    cls._apply_read_only(conn)
                    result = conn.execute(text(sql))
                    return [
                        {key: cls._json_safe(value) for key, value in dict(row).items()}
                        for row in result.mappings()
                    ]
        finally:
            engine.dispose()

    @staticmethod
    def _create_read_only_engine(plaintext_url: str) -> Engine:
        url = make_url(plaintext_url)
        connect_args: dict = {}
        render_url = plaintext_url

        if url.get_backend_name() == "sqlite":
            database = url.database
            if database and database != ":memory:":
                db_path = Path(database).expanduser().resolve()
                render_url = f"sqlite:///file:{db_path.as_posix()}?mode=ro&uri=true"
                connect_args["uri"] = True

        return create_engine(
            render_url,
            pool_pre_ping=True,
            poolclass=NullPool,
            connect_args=connect_args,
        )

    @staticmethod
    def _apply_read_only(conn) -> None:
        dialect = conn.dialect.name
        if dialect == "sqlite":
            conn.execute(text("PRAGMA query_only = ON"))
        elif dialect in {"postgresql", "postgres"}:
            conn.execute(text("SET TRANSACTION READ ONLY"))
        elif dialect in {"mysql", "mariadb"}:
            conn.execute(text("SET SESSION TRANSACTION READ ONLY"))

    @staticmethod
    def _read_only_sql(query: str | None, table: str | None) -> str:
        if query and query.strip():
            sql = query.strip().rstrip(";")
            if ";" in sql:
                raise ValueError("Multiple SQL statements are not allowed")
            lowered = sql.lower().lstrip()
            if not (lowered.startswith("select") or lowered.startswith("with")):
                raise ValueError("Only SELECT queries are allowed")
            padded = f" {lowered} "
            for token in _FORBIDDEN_SQL:
                if token in padded:
                    raise ValueError("Query is not read-only")
            return sql

        if not table or not _TABLE_NAME.match(table.strip()):
            raise ValueError("Invalid SQL table name")
        quoted = ".".join(f'"{part}"' for part in table.strip().split("."))
        return f"SELECT * FROM {quoted}"

    @staticmethod
    def _json_safe(value):
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, bytes):
            return value.decode("utf-8", "ignore")
        return value
