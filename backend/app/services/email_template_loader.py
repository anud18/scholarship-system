"""
Email Template Loader Service

⚠️ DEPRECATED: This module is kept for backward compatibility only.

New architecture (as of 2025-10-13):
- Frontend renders React Email templates with @react-email/render
- Frontend passes complete HTML to backend
- Backend only sends the email (no template loading/rendering)

This loader is used as a fallback when:
1. Old scheduled emails in database (without html_body)
2. Legacy code paths during migration

For new code, use EmailService.send_with_react_template() with html_content parameter.

---

Legacy behavior:
Loads and renders React Email exported HTML templates with variable substitution.
"""

import logging
import re
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class EmailTemplateLoader:
    """
    Load and process React Email exported HTML templates.

    Templates are exported from frontend/emails/*.tsx to frontend/public/email-templates/*.html
    This service loads the static HTML and performs simple {{variable}} replacement.
    """

    def __init__(self, template_dir: Optional[str] = None):
        """
        Initialize the template loader.

        Args:
            template_dir: Path to the email templates directory.
                         Defaults to frontend/public/email-templates relative to backend root.
        """
        if template_dir:
            self.template_dir = Path(template_dir)
        else:
            # Default: backend/../frontend/public/email-templates
            backend_dir = Path(__file__).parent.parent.parent  # backend/
            self.template_dir = backend_dir / ".." / "frontend" / "public" / "email-templates"

        self.template_dir = self.template_dir.resolve()
        self._cache: Dict[str, str] = {}

        logger.info(f"EmailTemplateLoader initialized with directory: {self.template_dir}")

        # Verify directory exists
        if not self.template_dir.exists():
            logger.warning(
                f"Email templates directory not found: {self.template_dir}. "
                "Templates may not be available. Run 'npm run email:export' in frontend directory."
            )

    def load_template(self, template_name: str) -> str:
        """
        Load HTML template from exported files.

        Args:
            template_name: Name of the template (without .html extension)

        Returns:
            HTML template content as string

        Raises:
            FileNotFoundError: If template file doesn't exist
        """
        # Check cache first
        if template_name in self._cache:
            logger.debug(f"Loading template '{template_name}' from cache")
            return self._cache[template_name]

        # Construct file path
        template_path = self.template_dir / f"{template_name}.html"

        if not template_path.exists():
            error_msg = (
                f"Email template not found: {template_name}.html\n"
                f"Expected path: {template_path}\n"
                f"Make sure to run 'npm run email:export' in the frontend directory."
            )
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        # Read template
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template_html = f.read()

            # Cache the template
            self._cache[template_name] = template_html
            logger.debug(f"Loaded and cached template: {template_name}")

            return template_html

        except Exception as e:
            logger.error(f"Error reading template file {template_path}: {e}")
            raise

    def render(self, template_name: str, context: Dict[str, str]) -> str:
        """
        Render template with context variables.

        Performs simple {{variableName}} → value replacement.

        Args:
            template_name: Name of the template to render
            context: Dictionary of variables to substitute

        Returns:
            Rendered HTML string with variables replaced

        Example:
            >>> loader = EmailTemplateLoader()
            >>> html = loader.render('application-submitted', {
            ...     'studentName': '王小明',
            ...     'appId': 'APP-001',
            ...     'scholarshipType': '學術優秀獎學金'
            ... })
        """
        # Load template
        template = self.load_template(template_name)

        # Replace variables: {{key}} → value
        rendered = template
        for key, value in context.items():
            placeholder = f"{{{{{key}}}}}"  # {{key}}
            rendered = rendered.replace(placeholder, str(value))

        # Check for any remaining unreplaced variables (for debugging)
        unreplaced = re.findall(r"\{\{(\w+)\}\}", rendered)
        if unreplaced:
            logger.warning(f"Template '{template_name}' has unreplaced variables: {unreplaced}")

        return rendered

    def clear_cache(self):
        """Clear the template cache. Useful for development/testing."""
        self._cache.clear()
        logger.info("Template cache cleared")

    def list_available_templates(self) -> list[str]:
        """
        List all available email templates.

        Returns:
            List of template names (without .html extension)
        """
        if not self.template_dir.exists():
            return []

        templates = []
        for file_path in self.template_dir.glob("*.html"):
            templates.append(file_path.stem)  # filename without extension

        return sorted(templates)


# Global instance for easy import
email_template_loader = EmailTemplateLoader()
