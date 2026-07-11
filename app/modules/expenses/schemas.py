from pydantic import BaseModel


class ExpenseOut(BaseModel):
    id: str
    tenant_id: str
    description: str
    value: float
    user_id: str
    created_at: str


class ExpenseCreate(BaseModel):
    description: str
    value: float
