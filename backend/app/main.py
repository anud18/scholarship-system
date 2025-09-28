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
from starlette.exceptions import HTTPException as StarletteHTTPException

# Import routers
from app.api.v1.api import api_router
from app.core.config import settings
from app.core.exceptions import ScholarshipException, scholarship_exception_handler

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events"""
    # Startup
    logger = logging.getLogger(__name__)
    try:
        logger.info("Starting application...")

        # Initialize the roster scheduler
        await init_scheduler()
        logger.info("Roster scheduler initialized")

        yield

    except Exception as e:
        logger.error(f"Error during application startup: {e}")
        raise
    finally:
        # Shutdown
        logger.info("Shutting down application...")
        try:
            await shutdown_scheduler()
            logger.info("Roster scheduler shut down")
        except Exception as e:
            logger.error(f"Error during scheduler shutdown: {e}")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="A comprehensive scholarship application and approval management system",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
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
        validation_logger.error(f"Validation error - Path: {request.url.path}, Method: {request.method}")
        validation_logger.error(f"Validation error - Headers (sanitized): {sanitized_headers}")
        validation_logger.error(f"Validation error - Field errors: {[error['loc'] for error in exc.errors()]}")
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
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Internal server error",
            "trace_id": getattr(request.state, "trace_id", None),
        },
    )


# Health check endpoint with database status
@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint including database status"""
    from app.core.database_health import check_database_health

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
    except Exception as e:
        # Get logger instance for this function
        health_logger = logging.getLogger(__name__)
        try:
            health_logger.error(f"Health check failed: {e}")
        except Exception:
            # Fallback logging if logger fails
            print(f"Health check failed (logger error): {e}")
        return {
            "success": False,
            "status": "unhealthy",
            "message": "Health check failed",
            "app_name": settings.app_name,
            "version": settings.app_version,
            "error": "Internal server error",
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
