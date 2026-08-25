from collections.abc import Iterator
from typing import Protocol


class CatalogConnector(Protocol):
    def stream_products(self) -> Iterator[dict]:
        ...
