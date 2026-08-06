"""Structured API errors for Cinesmith.

Every recoverable failure should return a stable machine-readable shape so the
UI can toast a clear message and offer a next action (open Settings, retry, etc.).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class CinesmithAPIError(Exception):
    """Raised for intentional, user-facing API failures."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "cinesmith_error",
        status_code: int = 400,
        hint: str = "",
        recovery: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.hint = hint
        self.recovery = recovery
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": "error",
            "error": {
                "code": self.code,
                "message": self.message,
                "hint": self.hint,
                "recovery": self.recovery,
                "details": self.details,
            },
        }


def error_payload(
    message: str,
    *,
    code: str = "cinesmith_error",
    hint: str = "",
    recovery: str = "",
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return CinesmithAPIError(
        message,
        code=code,
        hint=hint,
        recovery=recovery,
        details=details,
    ).to_dict()


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CinesmithAPIError)
    async def _cinesmith_api_error_handler(_request: Request, exc: CinesmithAPIError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())
