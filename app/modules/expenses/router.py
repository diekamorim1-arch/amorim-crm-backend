from fastapi import APIRouter, Depends

from app.core.auth import AuthContext
from app.deps import require_role, require_tenant
from app.modules.expenses import service
from app.modules.expenses.schemas import ExpenseCreate, ExpenseOut

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("", response_model=list[ExpenseOut])
def list_all(tenant_id: str = Depends(require_tenant)):
    return service.list_expenses(tenant_id)


@router.post("", response_model=ExpenseOut)
def create(body: ExpenseCreate, user: AuthContext = Depends(require_role("gestor"))):
    return service.create_expense(user.tenant_id, user.user_id, body.description, body.value)


@router.delete("/{expense_id}")
def delete(expense_id: str, user: AuthContext = Depends(require_role("gestor"))):
    service.delete_expense(user.tenant_id, user.user_id, expense_id)
    return {"status": "deleted"}
