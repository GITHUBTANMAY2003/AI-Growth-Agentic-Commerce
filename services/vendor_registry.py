from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = PROJECT_ROOT / "vendor_configs"
DATABASE_ROOT = PROJECT_ROOT / "database"
MOCK_VENDOR_DB = PROJECT_ROOT / "mock_vendor.db"
MOCK_VENDOR_TABLE = "vendor_catalog"


def mock_vendor_sqlite_url() -> str:
    return f"sqlite:///{MOCK_VENDOR_DB.resolve().as_posix()}"


def vendor_config_dir(vendor_id: int | str) -> Path:
    return CONFIG_ROOT / str(vendor_id)


def vendor_catalog_json(vendor_id: int | str) -> Path:
    return DATABASE_ROOT / str(vendor_id) / "products.json"


def _numeric_vendor_ids() -> set[int]:
    ids: set[int] = set()
    for root in (CONFIG_ROOT, DATABASE_ROOT):
        if not root.is_dir():
            continue
        for path in root.iterdir():
            if path.is_dir() and path.name.isdigit():
                ids.add(int(path.name))
    return ids


def next_vendor_id() -> int:
    ids = _numeric_vendor_ids()
    return (max(ids) if ids else 0) + 1


def register_vendor(name: str) -> dict:
    vendor_id = next_vendor_id()
    config_dir = vendor_config_dir(vendor_id)
    config_dir.mkdir(parents=True, exist_ok=True)
    vendor_file = config_dir / "vendor.yaml"
    vendor_file.write_text(
        yaml.safe_dump({"name": name.strip() or f"Vendor {vendor_id}"}, sort_keys=False),
        encoding="utf-8",
    )
    return {"vendor_id": vendor_id, "name": name.strip() or f"Vendor {vendor_id}"}


def _vendor_name(vendor_id: int) -> str | None:
    vendor_file = vendor_config_dir(vendor_id) / "vendor.yaml"
    if not vendor_file.is_file():
        return None
    payload = yaml.safe_load(vendor_file.read_text(encoding="utf-8")) or {}
    return payload.get("name")


def list_vendors() -> list[dict]:
    vendors = []
    for vendor_id in sorted(_numeric_vendor_ids()):
        config_path = vendor_config_dir(vendor_id) / "mapping.yaml"
        vendors.append(
            {
                "vendor_id": vendor_id,
                "name": _vendor_name(vendor_id),
                "has_mapping": config_path.is_file(),
                "has_catalog": vendor_catalog_json(vendor_id).is_file(),
            }
        )
    return vendors
