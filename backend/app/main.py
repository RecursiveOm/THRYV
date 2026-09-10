import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api import router
from app.config import Settings
from app.errors import AppError
from app.middleware import RequestBoundary

logger = logging.getLogger("thryv")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s %(message)s")
        # HTTP libraries' debug logs can contain request headers or provider details.
        for name in ("httpx", "httpcore", "uvicorn.access"):
            logging.getLogger(name).setLevel(logging.WARNING)
            logging.getLogger(name).disabled = True
        logger.info("THRYV starting")
        yield
        logger.info("THRYV stopped")

    app = FastAPI(
        title="THRYV",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.app_env == "development" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.app_env == "development" else None,
    )
    app.state.settings = settings

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        logger.warning("request_error request_id=%s code=%s", request.state.request_id, exc.code)
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # FastAPI's default validation errors echo user input. Never return exc.errors().
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_request",
                    "message": (
                        "Send a non-empty message of up to 8,000 characters "
                        "and valid recent conversation history."
                    ),
                }
            },
            status_code=422,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(
            {"error": {"code": "invalid_request", "message": "This request is not supported."}},
            status_code=exc.status_code,
        )

    app.include_router(router)
    app.add_middleware(RequestBoundary, max_concurrent=settings.max_concurrent_requests)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-ID"],
    )
    return app


app = create_app()
