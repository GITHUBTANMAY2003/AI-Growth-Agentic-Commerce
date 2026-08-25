from pydantic import BaseModel


class NormalizeRequest(BaseModel):
    vendor_id: int


class CreateVendorRequest(BaseModel):
    name: str = "Untitled vendor"


class CheckoutVerifyRequest(BaseModel):
    product_id: str


class SqlSourceRequest(BaseModel):
    database_url: str
