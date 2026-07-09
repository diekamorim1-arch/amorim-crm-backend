import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Pega qualquer exceção não tratada (KeyError, IndexError, erro do
        # client Supabase, etc.) para garantir que TODA resposta de erro siga
        # o envelope {"error": {"code", "message"}} — nunca o 500 cru padrão
        # do FastAPI/Starlette, que pode vazar stack trace/detalhes internos.
        logger.exception("Erro interno não tratado ao processar %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Erro interno no servidor."}},
        )
