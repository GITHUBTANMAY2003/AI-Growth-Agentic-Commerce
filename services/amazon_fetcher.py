from collections.abc import Iterator

from datasets import load_dataset

_KEEP_FIELDS = ("parent_asin", "title", "price", "categories", "description")


def stream_amazon_products() -> Iterator[dict]:
    dataset = load_dataset(
        "McAuley-Lab/Amazon-Reviews-2023",
        "raw_meta_Electronics",
        split="full",
        streaming=True,
        trust_remote_code=True,
    )
    # Mixed image schemas in this subset fail pyarrow casts; skip feature enforcement.
    if getattr(dataset, "_info", None) is not None:
        dataset._info.features = None
    for item in dataset:
        row = dict(item)
        yield {key: row.get(key) for key in _KEEP_FIELDS}
