import json
from pathlib import Path

from pydantic_models.product_types import AgentProduct
from services.amazon_fetcher import stream_amazon_products
from services.mapping_loader import load_product_mapping
from services.normalization_service import normalize_product

OUTPUT_PATH = Path(__file__).resolve().parent / "database" / "amazon" / "products.json"
TARGET_COUNT = 500


def sync_amazon_products(target_count: int = TARGET_COUNT, output_path: Path = OUTPUT_PATH) -> Path:
    mapping = load_product_mapping("amazon")
    products: list[AgentProduct] = []
    for raw_item in stream_amazon_products():
        product = normalize_product(raw_item, mapping)
        if product is None:
            continue
        products.append(product)
        if len(products) == target_count:
            break

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [product.model_dump() for product in products]
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output_path


if __name__ == "__main__":
    destination = sync_amazon_products()
    print(f"Wrote {TARGET_COUNT} products to {destination}")
