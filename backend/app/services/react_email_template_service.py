"""
React Email Template Service

Scans and provides metadata about React Email templates in the frontend/emails directory.
This service does NOT provide editing capabilities - templates are managed through Git
and edited in local development environments.
"""

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from app.core.path_security import validate_filename

logger = logging.getLogger(__name__)


class ReactEmailTemplateService:
    """Service for scanning and managing React Email template metadata"""

    # Path to React Email templates directory
    # Check environment variable first (for Docker), then fall back to relative path (for local dev)
    _template_dir_env = os.getenv("REACT_EMAIL_TEMPLATES_DIR")
    TEMPLATE_DIR = (
        Path(_template_dir_env)
        if _template_dir_env
        else (Path(__file__).parent.parent.parent.parent / "frontend" / "emails")
    )

    # Template display names and descriptions (can be moved to database later)
    TEMPLATE_METADATA = {
        "application-submitted": {
            "display_name": "申請送出通知",
            "description": "學生成功提交獎學金申請時發送給學生",
            "category": "application",
        },
        "professor-review-request": {
            "display_name": "教授審核請求",
            "description": "新申請需要教授推薦時發送給指導教授",
            "category": "review",
        },
        "college-review-request": {
            "display_name": "學院審核請求",
            "description": "教授推薦後需要學院審核時發送給學院",
            "category": "review",
        },
        "result-notification": {
            "display_name": "審核結果通知",
            "description": "最終審核結果出來時發送給學生、教授和學院",
            "category": "result",
        },
        "deadline-reminder": {
            "display_name": "截止日期提醒",
            "description": "申請截止日期前提醒學生儘快提交",
            "category": "reminder",
        },
        "document-request": {
            "display_name": "補件通知",
            "description": "需要學生補充文件時發送",
            "category": "supplement",
        },
        "roster-notification": {
            "display_name": "名冊通知",
            "description": "獎學金名冊確認時發送給獲獎學生",
            "category": "roster",
        },
        "whitelist-notification": {
            "display_name": "資格通知",
            "description": "獎學金申請開放時發送給符合資格的學生",
            "category": "whitelist",
        },
    }

    @classmethod
    def scan_templates(cls) -> List[Dict]:
        """
        Scan frontend/emails directory and return metadata for all React Email templates.

        Returns:
            List of template metadata dictionaries
        """
        templates = []

        if not cls.TEMPLATE_DIR.exists():
            logger.error(f"Template directory does not exist: {cls.TEMPLATE_DIR}")
            return templates

        # Scan all .tsx files (excluding _components directory)
        for file_path in cls.TEMPLATE_DIR.glob("*.tsx"):
            if file_path.name.startswith("_"):
                continue  # Skip component files

            try:
                metadata = cls._parse_template_file(file_path)
                if metadata:
                    templates.append(metadata)
            except Exception as e:
                logger.error(f"Failed to parse template {file_path.name}: {e}")
                continue

        # Sort by display name
        templates.sort(key=lambda t: t.get("display_name", t["name"]))

        return templates

    @classmethod
    def get_template(cls, template_name: str) -> Optional[Dict]:
        """
        Get metadata for a specific template.

        Args:
            template_name: Template name (e.g., "application-submitted")

        Returns:
            Template metadata or None if not found
        """
        # SECURITY: Validate template name to prevent path traversal
        try:
            validate_filename(f"{template_name}.tsx")
        except Exception as e:
            logger.warning(f"Invalid template name '{template_name}': {e}")
            return None

        file_path = cls.TEMPLATE_DIR / f"{template_name}.tsx"

        # SECURITY: Ensure resolved path is within TEMPLATE_DIR
        try:
            resolved_path = file_path.resolve(strict=False)
            template_dir = cls.TEMPLATE_DIR.resolve()
            if not str(resolved_path).startswith(str(template_dir)):
                logger.warning(f"Template path outside allowed directory: {resolved_path}")
                return None
        except Exception as e:
            logger.warning(f"Failed to resolve template path: {e}")
            return None

        if not file_path.exists():
            return None

        try:
            return cls._parse_template_file(file_path)
        except Exception as e:
            logger.error(f"Failed to parse template {template_name}: {e}")
            return None

    @classmethod
    def _parse_template_file(cls, file_path: Path) -> Optional[Dict]:
        """
        Parse a React Email template file to extract metadata.

        Args:
            file_path: Path to the .tsx file

        Returns:
            Template metadata dictionary
        """
        content = file_path.read_text(encoding="utf-8")
        template_name = file_path.stem

        # Extract Props interface to get variables
        variables = cls._extract_props_variables(content)

        # Get custom metadata or use defaults
        custom_metadata = cls.TEMPLATE_METADATA.get(template_name, {})

        # Get file stats
        stat = os.stat(file_path)
        last_modified = datetime.fromtimestamp(stat.st_mtime)

        return {
            "name": template_name,
            "display_name": custom_metadata.get("display_name", template_name.replace("-", " ").title()),
            "description": custom_metadata.get("description", "React Email template"),
            "category": custom_metadata.get("category", "general"),
            "file_path": str(file_path.relative_to(cls.TEMPLATE_DIR.parent.parent)),
            "variables": variables,
            "last_modified": last_modified.isoformat(),
            "file_size": stat.st_size,
        }

    @classmethod
    def _extract_props_variables(cls, content: str) -> List[Dict[str, str]]:
        """
        Extract variable names and types from Props interface.

        Args:
            content: File content

        Returns:
            List of variable metadata dictionaries
        """
        variables = []

        # Find Props interface definition
        # Pattern: interface SomethingProps { ... }
        props_pattern = r"interface\s+\w+Props\s*\{([^}]+)\}"
        props_match = re.search(props_pattern, content, re.DOTALL)

        if not props_match:
            return variables

        props_content = props_match.group(1)

        # Extract each property line
        # Pattern: variable_name?: string;
        var_pattern = r"(\w+)\??\s*:\s*([^;]+);"
        var_matches = re.findall(var_pattern, props_content)

        for var_name, var_type in var_matches:
            # Clean up type (remove extra whitespace)
            var_type = var_type.strip()

            # Extract default value from function parameters if available
            default_value = cls._extract_default_value(content, var_name)

            variables.append(
                {
                    "name": var_name,
                    "type": var_type,
                    "default_value": default_value,
                }
            )

        return variables

    @classmethod
    def _extract_default_value(cls, content: str, var_name: str) -> Optional[str]:
        """
        Extract default value for a variable from the template function.

        Args:
            content: File content
            var_name: Variable name

        Returns:
            Default value or None
        """
        # Pattern: variable_name = 'default_value' or variable_name = "default_value"
        default_pattern = rf"{var_name}\s*=\s*['\"]([^'\"]+)['\"]"
        default_match = re.search(default_pattern, content)

        if default_match:
            return default_match.group(1)

        return None

    @classmethod
    def get_template_source(cls, template_name: str) -> Optional[str]:
        """
        Get the source code of a template (for read-only viewing).

        Args:
            template_name: Template name

        Returns:
            Template source code or None
        """
        # SECURITY: Validate template name to prevent path traversal
        try:
            validate_filename(f"{template_name}.tsx")
        except Exception as e:
            logger.warning(f"Invalid template name '{template_name}': {e}")
            return None

        file_path = cls.TEMPLATE_DIR / f"{template_name}.tsx"

        # SECURITY: Ensure resolved path is within TEMPLATE_DIR
        try:
            resolved_path = file_path.resolve(strict=False)
            template_dir = cls.TEMPLATE_DIR.resolve()
            if not str(resolved_path).startswith(str(template_dir)):
                logger.warning(f"Template path outside allowed directory: {resolved_path}")
                return None
        except Exception as e:
            logger.warning(f"Failed to resolve template path: {e}")
            return None

        if not file_path.exists():
            return None

        try:
            return file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read template source {template_name}: {e}")
            return None
