from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from helpers.logging import get_logger, log_event

logger = get_logger("errors")


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class BadRequestError(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("bad_request", message, 400, details)


class SemanticError(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("semantic_error", message, 422, details)


class InterpretationError(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("interpretation_error", message, 500, details)


class OptimizationError(AppError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("optimization_error", message, 500, details)


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        log_event(
            logger,
            40 if exc.status_code >= 500 else 30,
            exc.message,
            code=exc.code,
            status_code=exc.status_code,
            details=exc.details,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = {
            "errors": [
                {"loc": error.get("loc"), "msg": error.get("msg"), "type": error.get("type")}
                for error in exc.errors()
            ]
        }
        log_event(logger, 30, "request validation failed", code="bad_request", details=details)
        return JSONResponse(
            status_code=400,
            content=error_body("bad_request", "Malformed or structurally invalid request", details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "http_error"
        if exc.status_code == 400:
            code = "bad_request"
        log_event(logger, 30, str(exc.detail), code=code, status_code=exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        log_event(logger, 40, "unhandled error", code="internal_error", error=str(exc))
        return JSONResponse(
            status_code=500,
            content=error_body("internal_error", "Internal server error"),
        )
