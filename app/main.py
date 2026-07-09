from fastapi import FastAPI

from app.core.errors import register_exception_handlers
from app.modules.activities.router import router as activities_router
from app.modules.appointments.router import router as appointments_router
from app.modules.auth.router import router as auth_router
from app.modules.connections.router import router as connections_router
from app.modules.contacts.router import router as contacts_router
from app.modules.conversations.router import router as conversations_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.deals.router import router as deals_router
from app.modules.suppliers.router import router as suppliers_router
from app.modules.tenants.router import router as tenants_router
from app.modules.users.router import router as users_router
from app.webhooks.evolution import router as evolution_webhook_router

app = FastAPI(title="Amorim CRM API")
register_exception_handlers(app)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(contacts_router, prefix="/api/v1")
app.include_router(deals_router, prefix="/api/v1")
app.include_router(suppliers_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(evolution_webhook_router, prefix="/api/v1")
app.include_router(appointments_router, prefix="/api/v1")
app.include_router(activities_router, prefix="/api/v1")
app.include_router(connections_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
