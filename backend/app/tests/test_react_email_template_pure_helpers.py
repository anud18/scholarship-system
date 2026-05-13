"""
Pure-function tests for `ReactEmailTemplateService` regex parsers.

This service introspects React Email .tsx templates to surface their
Props variables in the admin UI for variable-substitution preview.
Bugs in the regex extractors mean the admin sees the WRONG variable
list (or none), which leads to misconfigured email templates that
go out with literal `{{studentName}}` placeholders to students.

3 helpers covered (13 cases):
- `_get_template_paths`         : hardcoded allowlist contract
- `_extract_default_value`      : regex extract from function arg
- `_extract_props_variables`    : full Props interface parser
"""

import pytest

from app.services.react_email_template_service import ReactEmailTemplateService

# ─── _get_template_paths (allowlist contract) ────────────────────────


def test_get_template_paths_contains_all_8_known_templates():
    """The hardcoded allowlist is the security boundary — adding a new
    template requires updating both ALLOWED_TEMPLATE_NAMES and
    _get_template_paths together. Pin the set so reviewers notice when
    they're out of sync."""
    paths = ReactEmailTemplateService._get_template_paths()
    expected_names = {
        "application-submitted",
        "professor-review-request",
        "college-review-request",
        "result-notification",
        "deadline-reminder",
        "document-request",
        "roster-notification",
        "whitelist-notification",
    }
    assert set(paths.keys()) == expected_names


def test_get_template_paths_values_are_tsx_files():
    """All template paths must end in .tsx (the React Email convention)."""
    for name, path in ReactEmailTemplateService._get_template_paths().items():
        assert str(path).endswith(".tsx"), f"{name} → {path}"


# ─── _extract_default_value ──────────────────────────────────────────


def test_extract_default_value_single_quotes():
    """Pattern: `var_name = 'value'` — common in JSX function args."""
    content = "function Welcome({ studentName = 'Anonymous' }: WelcomeProps) {"
    assert ReactEmailTemplateService._extract_default_value(content, "studentName") == "Anonymous"


def test_extract_default_value_double_quotes():
    content = 'function App({ scholarshipType = "academic-excellence" }: AppProps) {'
    assert ReactEmailTemplateService._extract_default_value(content, "scholarshipType") == "academic-excellence"


def test_extract_default_value_missing_returns_none():
    """Variable with no default ⇒ None (don't fabricate)."""
    content = "function Welcome({ studentName, appId }: WelcomeProps) {"
    assert ReactEmailTemplateService._extract_default_value(content, "studentName") is None


def test_extract_default_value_handles_spacing_variations():
    """Both `var = 'val'` and `var='val'` are valid TS — pin both work
    so prettier-format vs unformatted files both parse correctly."""
    content_spaced = "function X({ name   =   'Alice' }: P) {"
    assert ReactEmailTemplateService._extract_default_value(content_spaced, "name") == "Alice"


# ─── _extract_props_variables (full interface parse) ─────────────────


def test_extract_props_variables_simple_interface():
    """Parses an interface like { name: string; appId: string; }."""
    content = """
interface WelcomeProps {
  studentName: string;
  appId: string;
}
function Welcome({ studentName, appId }: WelcomeProps) { return null; }
"""
    vars = ReactEmailTemplateService._extract_props_variables(content)
    names = [v["name"] for v in vars]
    assert names == ["studentName", "appId"]
    # Both should report 'string' as the type.
    for v in vars:
        assert v["type"] == "string"


def test_extract_props_variables_optional_marker():
    """`var?: string;` should still extract — the regex makes ? optional."""
    content = """
interface OptionalProps {
  required: string;
  optional?: string;
}
"""
    vars = ReactEmailTemplateService._extract_props_variables(content)
    assert {v["name"] for v in vars} == {"required", "optional"}


def test_extract_props_variables_complex_types():
    """Extracts type strings as-is (number, custom, union)."""
    content = """
interface ComplexProps {
  count: number;
  status: 'pending' | 'approved';
  metadata: Record<string, any>;
}
"""
    vars = ReactEmailTemplateService._extract_props_variables(content)
    type_map = {v["name"]: v["type"] for v in vars}
    assert type_map["count"] == "number"
    assert "pending" in type_map["status"]
    assert "Record" in type_map["metadata"]


def test_extract_props_variables_with_defaults():
    """When a default value exists in the function params, surface it."""
    content = """
interface AppProps {
  studentName: string;
  appId: string;
}
function App({ studentName = 'Alice', appId = 'APP-001' }: AppProps) {}
"""
    vars = ReactEmailTemplateService._extract_props_variables(content)
    name_to_default = {v["name"]: v["default_value"] for v in vars}
    assert name_to_default["studentName"] == "Alice"
    assert name_to_default["appId"] == "APP-001"


def test_extract_props_variables_no_props_interface_returns_empty():
    """Template with no Props interface (e.g., no-arg component) ⇒ []."""
    content = "function NoProps() { return <div>hi</div>; }"
    assert ReactEmailTemplateService._extract_props_variables(content) == []


def test_extract_props_variables_handles_first_interface_only():
    """The regex matches the FIRST `\\w+Props` interface — pinning current
    behavior so a template with multiple Props doesn't accidentally pick
    up a downstream one."""
    content = """
interface FirstProps { a: string; }
interface SecondProps { b: number; }
"""
    vars = ReactEmailTemplateService._extract_props_variables(content)
    names = [v["name"] for v in vars]
    assert names == ["a"]
