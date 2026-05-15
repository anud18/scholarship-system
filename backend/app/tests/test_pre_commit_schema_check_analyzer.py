"""
Tests for `backend/scripts/pre_commit_schema_check.py` —
APIEndpointAnalyzer (AST walker for FastAPI endpoint validation).

Script had ZERO test references. CI-CRITICAL: drives pre-commit
gate that catches response_model/raw-SQLAlchemy mismatches before
they ship. Drift in the validator silently lets endpoints pass
that should be flagged.

Wave 6a148 pins the validator branches by feeding synthetic Python
source through APIEndpointAnalyzer.analyze_file (via tempfile),
exercising the 3 issue types and the AST helpers.
"""

import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest

_SCRIPT_PATH = Path("/app/scripts/pre_commit_schema_check.py")
if not _SCRIPT_PATH.exists():
    _SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "pre_commit_schema_check.py"


@pytest.fixture(scope="module")
def script_module():
    spec = importlib.util.spec_from_file_location("pre_commit_schema_check", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pre_commit_schema_check"] = mod
    spec.loader.exec_module(mod)
    return mod


def _analyze(src: str, script_module) -> list:
    """Write src to a temp .py file and run the analyzer."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(src)
        path = f.name
    try:
        analyzer = script_module.APIEndpointAnalyzer()
        return analyzer.analyze_file(path)
    finally:
        Path(path).unlink(missing_ok=True)


class TestNoEndpointsClean:
    """Pin: file with no @router decorators → no issues."""

    def test_plain_function_no_issues(self, script_module):
        src = """
def regular_function():
    return 42
"""
        issues = _analyze(src, script_module)
        assert issues == []

    def test_unrelated_decorator_no_issues(self, script_module):
        # Pin: non-router decorators (@staticmethod, @pytest.fixture)
        # are NOT mistaken for FastAPI endpoints.
        src = """
@staticmethod
def helper():
    return 1
"""
        issues = _analyze(src, script_module)
        assert issues == []


class TestRawModelReturnDetection:
    """Pin: endpoint with response_model + bare-Name return
    flagged as 'raw_model_return'."""

    def test_response_model_with_bare_name_return_flagged(self, script_module):
        # Pin: bare Name return (e.g. `return user`) → raw_model_return.
        # No conversion to Pydantic; flag as error.
        src = """
@router.get("/users", response_model=UserResponse)
def get_users():
    user = db.query(User).first()
    return user
"""
        issues = _analyze(src, script_module)
        errors = [i for i in issues if i["type"] == "raw_model_return"]
        assert len(errors) == 1
        assert errors[0]["severity"] == "error"
        assert "raw SQLAlchemy" in errors[0]["message"]

    def test_response_model_with_query_all_flagged(self, script_module):
        # Pin: returning query.all() / .first() / .scalar_one() /
        # .scalars() also flagged.
        src = """
@router.get("/users", response_model=UserResponse)
def get_users():
    return db.query(User).all()
"""
        issues = _analyze(src, script_module)
        errors = [i for i in issues if i["type"] == "raw_model_return"]
        assert len(errors) == 1

    def test_response_model_with_explicit_response_wrapping_NOT_flagged(self, script_module):
        # Pin: when `UserResponse(...)` is in the function body
        # (has_conversion_logic), suppress raw_model_return.
        src = """
@router.get("/users", response_model=UserResponse)
def get_users():
    user = db.query(User).first()
    return UserResponse(id=user.id, name=user.name)
"""
        issues = _analyze(src, script_module)
        errors = [i for i in issues if i["type"] == "raw_model_return"]
        assert len(errors) == 0

    def test_no_response_model_NOT_flagged(self, script_module):
        # Pin: endpoint WITHOUT response_model not flagged for
        # raw return — pin so refactor to manual dict wrapping
        # (CLAUDE.md §5) doesn't trigger false positives.
        src = """
@router.get("/users")
def get_users():
    return db.query(User).all()
"""
        issues = _analyze(src, script_module)
        errors = [i for i in issues if i["type"] == "raw_model_return"]
        assert len(errors) == 0


class TestEnumSerializationCheck:
    """Pin: endpoint with response_model but no .value usage
    flagged as warning."""

    def test_response_model_without_dot_value_warning(self, script_module):
        # Pin: missing `.value` on potential enum fields →
        # warning (not error).
        src = """
@router.get("/users", response_model=UserResponse)
def get_users():
    return UserResponse(id=1, role="admin")
"""
        issues = _analyze(src, script_module)
        warnings = [i for i in issues if i["type"] == "missing_enum_serialization"]
        assert len(warnings) >= 1
        assert warnings[0]["severity"] == "warning"

    def test_response_model_with_dot_value_NOT_warned(self, script_module):
        # Pin: presence of `.value` suppresses the warning.
        src = """
@router.get("/users", response_model=UserResponse)
def get_users():
    return UserResponse(id=1, role=user.role.value)
"""
        issues = _analyze(src, script_module)
        warnings = [i for i in issues if i["type"] == "missing_enum_serialization"]
        assert len(warnings) == 0


class TestResponseModelNamingConvention:
    """Pin: response_model name should end with 'Response' (info-
    level issue, NOT blocking)."""

    def test_response_model_not_ending_with_Response_info(self, script_module):
        # Pin: 'UserModel' (no 'Response' suffix) → info-level issue.
        src = """
@router.get("/users", response_model=UserModel)
def get_users():
    return UserModel(id=1).value
"""
        issues = _analyze(src, script_module)
        info_issues = [i for i in issues if i["type"] == "response_model_naming"]
        assert len(info_issues) == 1
        assert info_issues[0]["severity"] == "info"

    def test_response_model_ending_with_Response_NOT_flagged(self, script_module):
        # Pin: 'UserResponse' → no naming issue.
        src = """
@router.get("/users", response_model=UserResponse)
def get_users():
    return UserResponse(id=1).value
"""
        issues = _analyze(src, script_module)
        info_issues = [i for i in issues if i["type"] == "response_model_naming"]
        assert len(info_issues) == 0


class TestExtractResponseModel:
    """Pin: _extract_response_model handles Name / Subscript / Attribute."""

    def test_simple_name(self, script_module):
        import ast

        analyzer = script_module.APIEndpointAnalyzer()
        node = ast.parse("UserResponse").body[0].value
        result = analyzer._extract_response_model(node)
        assert result == "UserResponse"

    def test_subscript_list_of_model(self, script_module):
        # Pin: List[UserResponse] returns the inner name "UserResponse".
        import ast

        analyzer = script_module.APIEndpointAnalyzer()
        node = ast.parse("List[UserResponse]").body[0].value
        result = analyzer._extract_response_model(node)
        assert result == "UserResponse"

    def test_attribute_returns_full_dotted_name(self, script_module):
        # Pin: schemas.UserResponse returns "schemas.UserResponse".
        import ast

        analyzer = script_module.APIEndpointAnalyzer()
        node = ast.parse("schemas.UserResponse").body[0].value
        result = analyzer._extract_response_model(node)
        assert result == "schemas.UserResponse"

    def test_unknown_node_returns_None(self, script_module):
        # Pin: unrecognized AST node → None.
        import ast

        analyzer = script_module.APIEndpointAnalyzer()
        node = ast.parse("1 + 2").body[0].value
        result = analyzer._extract_response_model(node)
        assert result is None


class TestParseErrorHandling:
    """Pin: malformed Python files produce parse_error issue (NOT crash)."""

    def test_malformed_python_produces_parse_error(self, script_module):
        # Pin: syntax error → recorded as parse_error issue
        # (severity=error). Pin so refactor doesn't crash the
        # pre-commit hook on malformed files.
        src = "def broken_(:\n    pass\n"
        issues = _analyze(src, script_module)
        parse_errors = [i for i in issues if i["type"] == "parse_error"]
        assert len(parse_errors) == 1
        assert parse_errors[0]["severity"] == "error"


class TestCheckFileWrapper:
    """Pin: top-level `check_file()` wrapper returns analyzer issues."""

    def test_check_file_returns_list(self, script_module):
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write("def x(): return 1\n")
            path = f.name
        try:
            issues = script_module.check_file(path)
            assert isinstance(issues, list)
        finally:
            Path(path).unlink(missing_ok=True)


class TestRouterMethodDetection:
    """Pin: only get/post/put/delete/patch decorators recognized."""

    @pytest.mark.parametrize("method", ["get", "post", "put", "delete", "patch"])
    def test_all_5_http_methods_recognized(self, method, script_module):
        # Pin: 5 HTTP verbs trigger endpoint analysis. Pin so
        # refactor doesn't drop one (PATCH/DELETE often missed).
        src = f"""
@router.{method}("/x", response_model=UserResponse)
def handler():
    return UserResponse(id=1).value
"""
        # No issues expected for well-formed endpoint, but it MUST
        # have been recognized (analyzer.endpoints non-empty).
        analyzer = script_module.APIEndpointAnalyzer()
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(src)
            path = f.name
        try:
            analyzer.analyze_file(path)
            assert len(analyzer.endpoints) == 1
            assert method in analyzer.endpoints[0]["methods"]
        finally:
            Path(path).unlink(missing_ok=True)

    def test_unknown_method_ignored(self, script_module):
        # Pin: unsupported method (e.g. @router.head) NOT analyzed.
        src = """
@router.head("/x", response_model=UserResponse)
def handler():
    return UserResponse(id=1).value
"""
        analyzer = script_module.APIEndpointAnalyzer()
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(src)
            path = f.name
        try:
            analyzer.analyze_file(path)
            assert len(analyzer.endpoints) == 0
        finally:
            Path(path).unlink(missing_ok=True)
