"""
Main FastAPI application entry point.
Configures middleware, exception handlers, and API routes.
"""

import json
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

# Import routers
from app.api.v1.api import api_router
from app.core.config import settings
from app.core.database_health import check_database_health
from app.core.exceptions import ScholarshipException, scholarship_exception_handler
from app.db.session import async_engine, sync_engine

# Import scheduler
from app.services.roster_scheduler_service import init_scheduler, shutdown_scheduler

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# 減少 SQLAlchemy 日誌噪音
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.dialects").setLevel(logging.WARNING)


# Create JSON formatter for structured logging
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)


# Configure root logger
root_logger = logging.getLogger()
if settings.log_format == "json":
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root_logger.addHandler(handler)

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Manage application lifespan events"""  # pylint: disable=unused-argument
    # Startup
    scheduler_started = False
    try:
        LOGGER.info("Starting application...")

        # Conditionally initialize the roster scheduler
        if settings.should_start_scheduler:
            await init_scheduler()
            scheduler_started = True
            LOGGER.info("Roster scheduler initialized")
        else:
            LOGGER.info("Roster scheduler disabled (test/CLI mode or explicitly disabled)")

        yield

    except Exception as exc:  # pylint: disable=broad-exception-caught
        LOGGER.exception("Error during application startup: %s", exc)
        raise
    finally:
        # Shutdown
        LOGGER.info("Shutting down application...")
        if scheduler_started:
            try:
                await shutdown_scheduler()
                LOGGER.info("Roster scheduler shut down")
            except Exception as exc:  # pylint: disable=broad-exception-caught
                LOGGER.exception("Error during scheduler shutdown: %s", exc)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="A comprehensive scholarship application and approval management system",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    lifespan=lifespan,
    redirect_slashes=False,  # Disable automatic slash redirects to prevent 307 in both dev and staging
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],  # Allow frontend to read filename from Content-Disposition header
)

# Add schema validation middleware (development only)
# Temporarily disabled due to logger scoping issue
# if settings.debug:
#     app.add_middleware(SchemaValidationMiddleware)


# Request tracing middleware
@app.middleware("http")
async def add_trace_id_middleware(request: Request, call_next):
    """Add trace ID to request for logging and debugging"""
    trace_id = str(uuid.uuid4())
    request.state.trace_id = trace_id

    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    return response


# Exception handlers
app.add_exception_handler(ScholarshipException, scholarship_exception_handler)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail,
            "trace_id": getattr(request.state, "trace_id", None),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors"""
    # Get logger instance for this function
    validation_logger = logging.getLogger(__name__)

    errors = []
    for error in exc.errors():
        field = " -> ".join(str(x) for x in error["loc"])
        message = error["msg"]
        errors.append(f"{field}: {message}")

    # Log sanitized error information for debugging
    sanitized_headers = {
        k: v
        for k, v in dict(request.headers).items()
        if k.lower() not in ["authorization", "cookie", "x-api-key", "x-auth-token"]
    }

    try:
        validation_logger.error(
            "Validation error - Path: %s, Method: %s",
            request.url.path,
            request.method,
        )
        validation_logger.error(
            "Validation error - Headers (sanitized): %s",
            sanitized_headers,
        )
        validation_logger.error(
            "Validation error - Field errors: %s",
            [error["loc"] for error in exc.errors()],
        )
    except Exception as log_error:
        # Fallback logging if logger fails
        print(f"Validation error (logger failed) - Path: {request.url.path}, Method: {request.method}")
        print(f"Logger error: {log_error}")
    # Do not log request body as it may contain sensitive data

    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": "Validation failed",
            "errors": errors,
            "trace_id": getattr(request.state, "trace_id", None),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):  # pylint: disable=broad-exception-caught
    """Handle unexpected exceptions"""
    # Get logger for this handler
    exception_logger = logging.getLogger(__name__)

    # Log the exception with full details
    trace_id = getattr(request.state, "trace_id", "unknown")
    exception_logger.error(
        "Unhandled exception - Trace ID: %s, Path: %s, Method: %s, Exception: %s: %s",
        trace_id,
        request.url.path,
        request.method,
        type(exc).__name__,
        exc,
        exc_info=True,
    )

    if isinstance(exc, (SQLAlchemyTimeoutError, OperationalError)):
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "message": "Service temporarily unavailable - database connection issue",
                "trace_id": trace_id,
            },
        )

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Internal server error",
            "trace_id": trace_id,
        },
    )


# Health check endpoint with database status
@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint including database status"""
    try:
        # Check database health
        db_health = await check_database_health()

        overall_status = "healthy" if db_health["status"] == "healthy" else "degraded"

        return {
            "success": True,
            "status": overall_status,
            "message": f"Service is {overall_status}",
            "app_name": settings.app_name,
            "version": settings.app_version,
            "database": {
                "status": db_health["status"],
                "connection": db_health["connection"],
                "pool_info": db_health.get("pool_info", {}),
                "cached_statement_error": db_health.get("cached_statement_error", False),
            },
        }
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Get logger instance for this function
        health_logger = logging.getLogger(__name__)
        try:
            health_logger.error("Health check failed: %s", exc)
        except Exception:
            # Fallback logging if logger fails
            print(
                f"Health check failed (logger error): {exc}",
            )
        return {
            "success": False,
            "status": "unhealthy",
            "message": "Health check failed",
            "app_name": settings.app_name,
            "version": settings.app_version,
            "error": "Internal server error",
        }


# Database pool status endpoint (admin only)
@app.get("/debug/pool-status")
async def get_pool_status():
    """Get current database connection pool status (for debugging)"""
    async_pool = async_engine.pool
    sync_pool = sync_engine.pool

    return {
        "success": True,
        "async_pool": {
            "size": async_pool.size(),
            "checked_in": async_pool.checkedin(),
            "checked_out": async_pool.checkedout(),
            "overflow": async_pool.overflow(),
            "total": async_pool.size() + async_pool.overflow(),
        },
        "sync_pool": {
            "size": sync_pool.size(),
            "checked_in": sync_pool.checkedin(),
            "checked_out": sync_pool.checkedout(),
            "overflow": sync_pool.overflow(),
            "total": sync_pool.size() + sync_pool.overflow(),
        },
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "success": True,
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "docs_url": "/api/v1/docs",
        "redoc_url": "/api/v1/redoc",
    }


# Include API routers
app.include_router(api_router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
    )
