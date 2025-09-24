"""
Development middleware to automatically validate API responses

This middleware runs in development mode to catch schema validation
errors immediately when endpoints are accessed.
"""

import json
import logging
import time
from typing import Any, Callable, Dict

from fastapi import Request, Response
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)


class SchemaValidationMiddleware(BaseHTTPMiddleware):
    """Middleware to validate API responses against declared schemas"""

    def __init__(self, app, enabled: bool = None):
        super().__init__(app)
        # Only enable in development mode by default
        self.enabled = enabled if enabled is not None else settings.debug
        self.validation_errors = []

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and validate response"""

        if not self.enabled:
            return await call_next(request)

        # Skip validation for certain paths
        if self._should_skip_validation(request.url.path):
            return await call_next(request)

        start_time = time.time()

        try:
            response = await call_next(request)

            # Only validate JSON responses
            if response.headers.get("content-type", "").startswith("application/json") and hasattr(response, "body"):
                await self._validate_response(request, response)

            return response

        except Exception as e:
            # Enhanced error handling for database-related issues
            try:
                error_message = str(e)

                # Check for PostgreSQL cached statement errors
                if (
                    "InvalidCachedStatementError" in error_message
                    or "cached statement plan is invalid" in error_message
                ):
                    logger.warning(f"Database cached statement error in middleware: {error_message}")
                    # Try to invalidate connection pools to resolve the issue
                    try:
                        from app.db.session import invalidate_connection_pools_sync

                        invalidate_connection_pools_sync()
                        logger.info("Connection pools invalidated due to cached statement error")
                    except ImportError:
                        pass
                else:
                    # Log other errors normally
                    logger.error(f"Schema validation middleware error: {e}")
            except Exception as log_error:
                # Fallback logging if logger fails
                print(f"Schema validation middleware error (logger failed): {e}")
                print(f"Logger error: {log_error}")

            # Always continue with the request, don't break the application
            return await call_next(request)

        finally:
            process_time = time.time() - start_time
            logger.debug(f"Schema validation took {process_time:.4f}s for {request.url.path}")

    def _should_skip_validation(self, path: str) -> bool:
        """Check if we should skip validation for this path"""
        skip_paths = [
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/static",
            "/favicon.ico",
        ]

        return any(path.startswith(skip_path) for skip_path in skip_paths)

    async def _validate_response(self, request: Request, response: Response):
        """Validate response against expected schema"""
        try:
            # Get response body
            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            # Parse JSON
            if body:
                try:
                    response_data = json.loads(body.decode())
                except json.JSONDecodeError:
                    return  # Not JSON, skip validation
            else:
                response_data = None

            # Find the route and expected response model
            route_info = self._get_route_info(request)
            if not route_info or not route_info.get("response_model"):
                return

            # Validate against schema
            response_model = route_info["response_model"]
            self._perform_validation(response_data, response_model, request.url.path, request.method)

        except Exception as e:
            logger.error(f"Response validation error: {e}")

    def _get_route_info(self, request: Request) -> Dict[str, Any]:
        """Get route information including response model"""
        try:
            # This is a simplified version - in practice, you'd need to
            # extract this from FastAPI's route information
            route = request.scope.get("route")
            if route and hasattr(route, "response_model"):
                return {
                    "response_model": route.response_model,
                    "path": route.path,
                    "methods": route.methods,
                }
        except Exception:
            pass

        return {}

    def _perform_validation(self, data: Any, response_model: type, path: str, method: str):
        """Perform actual validation and log issues"""
        try:
            if isinstance(data, list):
                for item in data:
                    response_model.model_validate(item) if hasattr(
                        response_model, "model_validate"
                    ) else response_model(**item)
            else:
                response_model.model_validate(data) if hasattr(response_model, "model_validate") else response_model(
                    **data
                )

            logger.debug(f"✅ Schema validation passed for {method} {path}")

        except ValidationError as e:
            error_info = {
                "path": path,
                "method": method,
                "errors": e.errors(),
                "timestamp": time.time(),
            }

            self.validation_errors.append(error_info)

            # Log detailed error information
            logger.error(f"❌ Schema validation failed for {method} {path}")
            for error in e.errors():
                field_path = " -> ".join(str(loc) for loc in error["loc"])
                logger.error(f"   Field '{field_path}': {error['msg']}")

            # In development, you might want to be more aggressive
            if settings.debug:
                logger.error("Response data structure:")
                logger.error(json.dumps(data, indent=2, default=str))

        except Exception as e:
            logger.error(f"Validation error: {e}")

    def get_validation_errors(self) -> list:
        """Get all validation errors collected by this middleware"""
        return self.validation_errors.copy()

    def clear_validation_errors(self):
        """Clear validation error history"""
        self.validation_errors.clear()


# Enhanced response validation decorator
def validate_response_in_dev(response_model: type):
    """
    Decorator to validate responses in development mode

    This provides immediate feedback when developing endpoints
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            # Only validate in development
            if settings.debug:
                try:
                    if isinstance(result, list):
                        for item in result:
                            response_model.model_validate(item) if hasattr(
                                response_model, "model_validate"
                            ) else response_model(**item)
                    else:
                        response_model.model_validate(result) if hasattr(
                            response_model, "model_validate"
                        ) else response_model(**result)

                    logger.debug(f"✅ Response validation passed for {func.__name__}")

                except ValidationError as e:
                    logger.error(f"❌ Response validation failed for {func.__name__}")
                    for error in e.errors():
                        field_path = " -> ".join(str(loc) for loc in error["loc"])
                        logger.error(f"   Field '{field_path}': {error['msg']}")

                    # Log the actual data structure for debugging
                    logger.error("Actual response data:")
                    logger.error(json.dumps(result, indent=2, default=str))

                    # In strict development mode, raise the error
                    if settings.environment == "development":
                        raise

            return result

        return wrapper

    return decorator


# Development endpoint to check validation status
def create_validation_status_endpoint(middleware_instance: SchemaValidationMiddleware):
    """Create an endpoint to check validation status during development"""

    async def get_validation_status():
        """Get current validation error status"""
        errors = middleware_instance.get_validation_errors()

        return {
            "validation_enabled": middleware_instance.enabled,
            "total_errors": len(errors),
            "recent_errors": errors[-10:] if errors else [],  # Last 10 errors
            "error_summary": {"by_endpoint": {}, "by_error_type": {}},
        }

    return get_validation_status
