"""Basic FastAPI session API; AI-assisted from docs/frontend-contract.md.

Import creates an app object only. No private YAML or session data is read and
no directories are written until an explicit session operation needs them.
"""

import logging
import os
from collections.abc import Callable
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.catalog import CompetitionCatalog
from backend.config import Settings
from backend.schemas import (
    AgentRunner,
    AppError,
    CompetitionDetail,
    CreateSessionRequest,
    ErrorDetail,
    ErrorResponse,
    ProfilePatchRequest,
    SessionSnapshot,
)
from backend.service import SessionService
from backend.storage import SessionStore

logger = logging.getLogger(__name__)


def _error_response(error: AppError) -> JSONResponse:
    envelope = ErrorResponse(
        error=ErrorDetail(
            code=error.code,
            message=error.message,
            retryable=error.retryable,
            details=error.details,
        )
    )
    return JSONResponse(status_code=error.status_code, content=envelope.model_dump(mode="json"))


class _SafeHTTPErrorBoundary:
    """Consume ordinary HTTP failures before Starlette/Uvicorn can log their content."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception:
            # Never log the exception, its class name, traceback, or request content.
            # CancelledError is a BaseException and must propagate through this boundary.
            logger.error("HTTP request failed: INTERNAL_ERROR")
            if not response_started:
                response = _error_response(
                    AppError(
                        "INTERNAL_ERROR",
                        "服务暂不可用，请稍后重试。",
                        500,
                    )
                )
                await response(scope, receive, send)
            # A response already started cannot be replaced. Do not emit a second
            # response or rethrow sensitive data; the server closes an incomplete body.


def create_app(
    settings: Settings | None = None,
    agent: AgentRunner | None = None,
    clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    settings = settings if settings is not None else Settings.from_sources(os.environ, None)
    service = SessionService(
        SessionStore(settings.data_dir / "sessions", boundary=settings.data_dir),
        agent,
        catalog=CompetitionCatalog(settings.catalog_path),
        clock=clock,
    )
    application = FastAPI(debug=False)
    application.state.settings = settings
    application.state.service = service
    # Last added middleware runs outermost: CORS must see the safe 500 response.
    application.add_middleware(_SafeHTTPErrorBoundary)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
    )

    @application.exception_handler(AppError)
    async def controlled_error(request: Request, error: AppError) -> JSONResponse:
        return _error_response(error)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        # Even errors(include_input=False) can expose input through ctx/msg/loc.
        # Do not echo validation objects, untrusted field names, or the request body.
        return _error_response(AppError("VALIDATION_ERROR", "请求字段无效，请检查后重试。", 422))

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(error.status_code, "HTTP_ERROR")
        response = _error_response(AppError(code, "请求的资源或方法不可用。", error.status_code))
        if error.headers and "Allow" in error.headers:
            response.headers["Allow"] = error.headers["Allow"]
        return response

    @application.post("/api/sessions", status_code=201, response_model=SessionSnapshot)
    async def create_session(body: CreateSessionRequest) -> SessionSnapshot:
        return service.create_session()

    @application.get("/api/sessions/{session_id}", response_model=SessionSnapshot)
    async def get_session(session_id: str) -> SessionSnapshot:
        return service.get_session(session_id)

    @application.patch("/api/sessions/{session_id}/profile", response_model=SessionSnapshot)
    async def patch_profile(session_id: str, body: ProfilePatchRequest) -> SessionSnapshot:
        return await service.patch_profile(session_id, body)

    @application.get("/api/competitions/{instance_id}", response_model=CompetitionDetail)
    async def get_competition(instance_id: str) -> CompetitionDetail:
        return service.get_competition(instance_id)

    return application


app = create_app()
