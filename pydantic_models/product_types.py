from pydantic import BaseModel, Field


class AgentProduct(BaseModel):
    id: str
    title: str
    price_in_cents: int = 0
    categories: list[str] = Field(default_factory=list)
    description: str = ""
