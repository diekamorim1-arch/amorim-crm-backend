from fastapi import FastAPI

from app.core.errors import register_exception_handlers
from app.modules.auth.router import router as auth_router
from app.modules.tenants.router import router as tenants_router
from app.modules.users.router import router as users_router

app = FastAPI(title="Amorim CRM API")
register_exception_handlers(app)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
