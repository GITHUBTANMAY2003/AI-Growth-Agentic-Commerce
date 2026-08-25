"""Catalog connectors implement one contract: stream raw product dicts.

Today: SqlConnector (relational via SQLAlchemy).
Tomorrow: MongoConnector / FirestoreConnector / RestConnector — same Protocol,
register the builder in services.ingest_service._CONNECTOR_BUILDERS.
"""

from services.connectors.base import CatalogConnector
from services.connectors.sql_connector import SqlConnector

__all__ = ["CatalogConnector", "SqlConnector"]
