"""
Frontend Email Renderer Service

Calls the frontend Next.js API to render React Email templates.

Architecture:
- Backend creates context with actual data (snake_case variables)
- Frontend renders React Email templates with @react-email/render
- Backend receives complete HTML and sends via email

This approach allows:
- React Email templates can be edited dynamically without rebuilding backend
- Frontend handles all template rendering logic
- Backend only needs to send the email
"""

import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


async def render_email_via_frontend(
    frontend_url: str,
    template_name: str,
    context: Dict[str, Any],
) -> Optional[str]:
    """
    Call frontend API to render email template.

    Args:
        frontend_url: Base URL of frontend (e.g., "http://frontend:3000")
        template_name: Name of the email template (e.g., "application-submitted")
        context: Dictionary with template variables (snake_case)

    Returns:
        Rendered HTML string, or None if rendering failed

    Example:
        >>> html = await render_email_via_frontend(
        ...     frontend_url="http://frontend:3000",
        ...     template_name="application-submitted",
        ...     context={
        ...         "student_name": "王小明",
        ...         "app_id": "APP-2025-826055",
        ...         "scholarship_type": "學術優秀獎學金",
        ...         "submit_date": "2025-10-13",
        ...         "professor_name": "李教授",
        ...         "system_url": "https://scholarship.nycu.edu.tw"
        ...     }
        ... )
    """
    render_endpoint = f"{frontend_url}/api/email/render"

    try:
        logger.info(f"Calling frontend to render template '{template_name}'")
        logger.debug(f"Render endpoint: {render_endpoint}")
        logger.debug(f"Context keys: {list(context.keys())}")

        # Call frontend API with timeout
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                render_endpoint,
                json={
                    "template_name": template_name,
                    "context": context,
                },
            )

            # Check response status
            if response.status_code != 200:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("error", "Unknown error")
                logger.error(f"Frontend API returned error (status {response.status_code}): {error_msg}")
                return None

            # Parse response
            result = response.json()

            if not result.get("success"):
                error_msg = result.get("error", "Unknown error")
                logger.error(f"Frontend rendering failed: {error_msg}")
                return None

            # Extract HTML
            html = result.get("html")
            if not html:
                logger.error("Frontend returned success but no HTML content")
                return None

            logger.info(f"Successfully rendered template '{template_name}' ({len(html)} chars)")
            return html

    except httpx.TimeoutException:
        logger.error(f"Timeout calling frontend email renderer at {render_endpoint} " f"(template: {template_name})")
        return None

    except httpx.ConnectError as e:
        logger.error(
            f"Connection error calling frontend at {render_endpoint}: {e}. "
            f"Make sure frontend container is running and FRONTEND_URL is correct."
        )
        return None

    except Exception as e:
        logger.error(
            f"Unexpected error rendering email via frontend " f"(template: {template_name}): {e}", exc_info=True
        )
        return None
