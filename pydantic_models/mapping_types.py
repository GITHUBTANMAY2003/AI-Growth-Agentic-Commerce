from pydantic import BaseModel, Field


class ProductFieldMapping(BaseModel):
    """Maps vendor-specific column names onto AgentProduct fields."""

    id: str
    title: str
    price: str
    description: str
    categories: str | None = None
    source: str | None = Field(
        default=None,
        description="Connector kind: sql today; future: mongodb, firestore, rest, etc.",
    )


IDENTITY_PRODUCT_MAPPING = ProductFieldMapping(
    id="id",
    title="title",
    price="price",
    description="description",
    categories="categories",
    source="sql",
)


class SqlSourceConfig(BaseModel):
    encrypted_url: str
    query: str | None = None
    table: str | None = None
    id_column: str | None = None
    stock_column: str | None = None


class VendorConfig(BaseModel):
    source: str | None = "sql"
    mapping: ProductFieldMapping | None = None
    sql: SqlSourceConfig | None = None
