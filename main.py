from fastapi import FastAPI, HTTPException
import uvicorn

from pydantic_models.request_types import (
    CheckoutVerifyRequest,
    CreateVendorRequest,
    NormalizeRequest,
    SqlSourceRequest,
)
from services.ai_schema_mapper import onboard_vendor_sql
from services.ingest_service import load_normalized_catalog, save_sql_source, sync_vendor
from services.inventory_service import verify_in_stock
from services.mapping_loader import load_vendor_config
from services.vendor_registry import list_vendors, register_vendor

app = FastAPI(title="Agent Native Commerce — Enterprise SQL Ingest")


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=500, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@app.get("/")
def read_root():
    return {"message": "Welcome to the FastAPI server!"}


@app.post("/vendors")
def create_vendor(request: CreateVendorRequest):
    return register_vendor(request.name)


@app.get("/vendors")
def get_vendors():
    return {"vendors": list_vendors()}


@app.get("/vendors/{vendor_id}/mapping")
def get_mapping(vendor_id: int):
    try:
        config = load_vendor_config(vendor_id)
    except (FileNotFoundError, ValueError) as exc:
        raise _http_error(exc) from exc
    payload = config.mapping.model_dump() if config.mapping else {}
    if config.sql is not None:
        payload["sql"] = config.sql.model_dump()
    payload["source"] = config.source
    return payload


@app.post("/vendors/{vendor_id}/sql-source")
def upsert_sql_source(vendor_id: int, request: SqlSourceRequest):
    try:
        save_sql_source(vendor_id, request)
        return onboard_vendor_sql(vendor_id)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise _http_error(exc) from exc


@app.post("/vendors/{vendor_id}/onboard")
def onboard_vendor(vendor_id: int):
    try:
        return onboard_vendor_sql(vendor_id)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise _http_error(exc) from exc


@app.post("/vendors/{vendor_id}/sync")
def sync_vendor_catalog(vendor_id: int):
    try:
        return sync_vendor(vendor_id)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise _http_error(exc) from exc


@app.get("/vendors/{vendor_id}/products")
def get_vendor_products(vendor_id: int):
    try:
        products = load_normalized_catalog(vendor_id)
    except FileNotFoundError as exc:
        raise _http_error(exc) from exc
    return {"vendor_id": vendor_id, "count": len(products), "products": products}


@app.post("/vendors/{vendor_id}/checkout/verify")
def verify_checkout_stock(vendor_id: int, request: CheckoutVerifyRequest):
    try:
        available = verify_in_stock(vendor_id, request.product_id)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise _http_error(exc) from exc
    return {"status": "available" if available else "out_of_stock"}


@app.post("/sync")
def sync_data(request: NormalizeRequest):
    try:
        result = sync_vendor(request.vendor_id)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise _http_error(exc) from exc
    return {"message": "Data normalization completed successfully.", **result}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
