from pydantic import BaseModel, Field


class QuotaResponse(BaseModel):
    used_bytes: int
    limit_bytes: int = Field(ge=0)
    private_bytes: int
    private_limit_bytes: int = Field(ge=0)
