"""
Tests for `ConfigCategory` and `ConfigDataType` enums in
`app.models.system_setting`.

These drive the admin Configuration Management UI:
- ConfigCategory groups settings into tabs (database / api_keys / email
  / ocr / file_storage / security / features / integrations /
  performance / logging)
- ConfigDataType is the validation contract — each value-string format
  is enforced by ConfigManagementService (covered in wave 6m)

SECURITY-RELEVANT: api_keys + security categories contain credentials.
A rename here without updating the admin UI's permission check would
silently make them editable by lower-privileged users.

2 enums (4 cases). Pure, no DB.
"""

from app.models.system_setting import ConfigCategory, ConfigDataType

# ─── ConfigCategory ──────────────────────────────────────────────────


def test_config_category_values():
    """Pin: 10 category values. The admin Configuration Management UI
    groups settings into tabs by this enum — rename orphans settings
    from their tab."""
    assert ConfigCategory.database.value == "database"
    assert ConfigCategory.api_keys.value == "api_keys"
    assert ConfigCategory.email.value == "email"
    assert ConfigCategory.ocr.value == "ocr"
    assert ConfigCategory.file_storage.value == "file_storage"
    assert ConfigCategory.security.value == "security"
    assert ConfigCategory.features.value == "features"
    assert ConfigCategory.integrations.value == "integrations"
    assert ConfigCategory.performance.value == "performance"
    assert ConfigCategory.logging.value == "logging"
    assert len(list(ConfigCategory)) == 10


def test_config_category_security_categories_pinned():
    """SECURITY-CRITICAL: api_keys + security are the two categories
    holding credentials. Pin both string values explicitly so a refactor
    that renames them (and forgets to update the admin UI's permission
    gate) makes the test fail loudly."""
    assert ConfigCategory.api_keys.value == "api_keys"  # holds SMTP password, Gemini key, etc.
    assert ConfigCategory.security.value == "security"  # holds JWT secret, etc.


# ─── ConfigDataType ──────────────────────────────────────────────────


def test_config_data_type_values():
    """Pin: 5 data types. ConfigManagementService.validate_value
    (covered in wave 6m) routes validation based on these strings."""
    assert ConfigDataType.string.value == "string"
    assert ConfigDataType.integer.value == "integer"
    assert ConfigDataType.boolean.value == "boolean"
    assert ConfigDataType.json.value == "json"
    assert ConfigDataType.float.value == "float"
    assert len(list(ConfigDataType)) == 5


def test_config_data_type_python_keyword_avoidance():
    """Pin: 'json' is a valid Python identifier (no clash). 'integer'
    and 'float' chosen to avoid clashing with Python's int/float
    builtins. Pin the names so a refactor renaming to int/float
    causes a syntax-level surface immediately."""
    # These names are valid Python identifiers
    for member in (
        ConfigDataType.string,
        ConfigDataType.integer,
        ConfigDataType.boolean,
        ConfigDataType.json,
        ConfigDataType.float,
    ):
        # name attribute access works
        assert isinstance(member.name, str)
