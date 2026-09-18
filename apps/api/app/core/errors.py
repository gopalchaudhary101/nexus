"""Exception types + FastAPI handlers."""
from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, detail: str, *, code: str = "error") -> None:
        super().__init__(detail)
        self.detail = detail
        self.code = code


class NotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, detail: str = "Not found") -> None:
        super().__init__(detail, code="not_found")


class Forbidden(ApiError):
    status_code = status.HTTP_403_FORBIDDEN

    def __init__(self, detail: str = "Forbidden") -> None:
        super().__init__(detail, code="forbidden")


class Unauthorized(ApiError):
    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self, detail: str = "Unauthorized") -> None:
        super().__init__(detail, code="unauthorized")


class RateLimited(ApiError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS

    def __init__(self, detail: str = "Rate limit exceeded") -> None:
        super().__init__(detail, code="rate_limited")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code,
                            content={"error": {"code": exc.code, "detail": exc.detail}})

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"code": "validation", "detail": exc.errors()}},
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Do not leak internals.
        return JSONResponse(status_code=500,
                            content={"error": {"code": "internal", "detail": "Internal server error"}})
