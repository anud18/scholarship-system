from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.application import ApplicationStatus
from app.services import eligibility_service as eligibility_service_module
from app.services.eligibility_service import EligibilityService


class StubScalarSequence:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)


class StubResult:
    def __init__(self, scalars=None, scalar=None, rows=None):
        self._scalars = scalars or []
        self._scalar = scalar
        self._rows = rows or []

    def scalars(self):
        return StubScalarSequence(self._scalars)

    def scalar_one_or_none(self):
        return self._scalar

    def fetchall(self):
        return list(self._rows)


class StubSession:
    def __init__(self, responses=None):
        self._responses = list(responses or [])
        self.executed = []

    async def execute(self, stmt, params=None):
        self.executed.append((stmt, params))
        if not self._responses:
            raise AssertionError("No more stubbed responses available")
        return self._responses.pop(0)


def build_config(**overrides):
    base = {
        "is_active": True,
        "is_effective": True,
        "application_start_date": datetime.now(timezone.utc) - timedelta(days=1),
        "application_end_date": datetime.now(timezone.utc) + timedelta(days=1),
        "renewal_application_start_date": None,
        "renewal_application_end_date": None,
        "scholarship_type": SimpleNamespace(whitelist_enabled=False),
        "whitelist_student_ids": None,
        "scholarship_type_id": 1,
        "academic_year": "2024",
        "semester": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def build_rule(**overrides):
    defaults = {
        "id": 1,
        "rule_name": "GPA requirement",
        "rule_type": "student",
        "condition_field": "gpa",
        "expected_value": "3.0",
        "operator": ">=",
        "message": "GPA too low",
        "message_en": "GPA too low",
        "is_active": True,
        "is_template": False,
        "is_initial_enabled": True,
        "is_warning": False,
        "is_hard_rule": True,
        "sub_type": None,
        "tag": "academic",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_is_dev_mode_and_bypass_flags(monkeypatch):
    service = EligibilityService(db=StubSession())
    monkeypatch.setattr(eligibility_service_module.settings, "debug", True, raising=False)
    monkeypatch.setitem(eligibility_service_module.DEV_SCHOLARSHIP_SETTINGS, "BYPASS_WHITELIST", True)
    monkeypatch.setitem(eligibility_service_module.DEV_SCHOLARSHIP_SETTINGS, "ALWAYS_OPEN_APPLICATION", False)

    assert service._is_dev_mode() is True
    assert service._should_bypass_whitelist() is True
    assert service._should_bypass_application_period() is False

    monkeypatch.setattr(eligibility_service_module.settings, "debug", False, raising=False)
    monkeypatch.setattr(eligibility_service_module.settings, "environment", "production", raising=False)
    monkeypatch.setitem(eligibility_service_module.DEV_SCHOLARSHIP_SETTINGS, "ALWAYS_OPEN_APPLICATION", True)

    assert service._is_dev_mode() is False
    assert service._should_bypass_whitelist() is False
    assert service._should_bypass_application_period() is False


@pytest.mark.asyncio
async def test_check_student_eligibility_handles_inactive_config(monkeypatch):
    config = build_config(is_active=False)
    service = EligibilityService(db=StubSession())

    eligible, reasons = await service.check_student_eligibility({"gpa": 4.0}, config)

    assert eligible is False
    assert "獎學金配置未啟用" in reasons


@pytest.mark.asyncio
async def test_check_student_eligibility_period_and_whitelist(monkeypatch):
    now = datetime.now(timezone.utc)
    config = build_config(
        application_start_date=now - timedelta(days=10),
        application_end_date=now - timedelta(days=5),
        renewal_application_start_date=None,
        renewal_application_end_date=None,
        scholarship_type=SimpleNamespace(whitelist_enabled=True),
        whitelist_student_ids={"999": True},
    )

    monkeypatch.setattr(eligibility_service_module.settings, "debug", False, raising=False)
    monkeypatch.setitem(eligibility_service_module.DEV_SCHOLARSHIP_SETTINGS, "BYPASS_WHITELIST", False)
    monkeypatch.setitem(eligibility_service_module.DEV_SCHOLARSHIP_SETTINGS, "ALWAYS_OPEN_APPLICATION", False)

    service = EligibilityService(db=StubSession([StubResult(scalars=[])]))

    async def fake_rules(student_data, cfg):
        return True, []

    monkeypatch.setattr(service, "_check_scholarship_rules", fake_rules)

    eligible, reasons = await service.check_student_eligibility({"std_stdcode": "123"}, config)

    assert eligible is False
    assert "未在白名單中" in reasons
    assert "不在申請期間內" in reasons


@pytest.mark.asyncio
async def test_check_student_eligibility_passes_rules(monkeypatch):
    config = build_config()
    service = EligibilityService(db=StubSession([StubResult(scalars=[])]))

    async def fake_rules(student_data, cfg):
        return True, []

    monkeypatch.setattr(service, "_check_scholarship_rules", fake_rules)

    eligible, reasons = await service.check_student_eligibility({"std_stdcode": "1", "gpa": 3.5}, config)

    assert eligible is True
    assert reasons == []


@pytest.mark.asyncio
async def test_check_rules_collects_failures():
    student = {"gpa": 2.5, "major": "EE", "clubs": "math,science"}
    rule_pass = build_rule(id=1, rule_name="GPA min", condition_field="gpa", operator=">=", expected_value="2.0")
    rule_fail_hard = build_rule(id=2, rule_name="GPA strict", expected_value="3.0")
    rule_warning = build_rule(
        id=3,
        rule_name="Club",
        condition_field="clubs",
        operator="contains",
        expected_value="robotics",
        is_warning=True,
        is_hard_rule=False,
    )
    rule_subtype = build_rule(
        id=4,
        rule_name="Subtype GPA",
        expected_value="3.5",
        sub_type="SPECIAL",
        message="Subtype requirement",
    )

    config = build_config()
    session = StubSession([StubResult(scalars=[rule_pass, rule_fail_hard, rule_warning, rule_subtype])])
    service = EligibilityService(db=session)

    passed, failures = await service._check_scholarship_rules(student, config)

    assert passed is False
    assert "Subtype requirement" in failures
    assert any("不符合" in reason for reason in failures)


@pytest.mark.asyncio
async def test_check_rules_detailed_groups_results():
    student = {"gpa": 3.6, "clubs": "robotics"}
    rule_pass = build_rule(id=1, rule_name="GPA", expected_value="3.0")
    rule_soft_fail = build_rule(
        id=2,
        rule_name="Soft",
        expected_value="3.8",
        is_hard_rule=False,
        message="Soft miss",
    )
    rule_warn = build_rule(
        id=3,
        rule_name="Warn",
        operator="contains",
        condition_field="clubs",
        expected_value="math",
        is_hard_rule=False,
        is_warning=True,
    )
    rule_subtype = build_rule(
        id=4,
        rule_name="Subtype",
        expected_value="4.0",
        sub_type="A",
        message="Subtype fail",
    )

    config = build_config()
    session = StubSession([StubResult(scalars=[rule_pass, rule_soft_fail, rule_warn, rule_subtype])])
    service = EligibilityService(db=session)

    passed, failures, details = await service._check_scholarship_rules_detailed(student, config)

    assert passed is False
    assert "Subtype fail" in failures
    assert len(details["passed"]) == 1
    assert len(details["warnings"]) == 1
    assert len(details["errors"]) == 2


def test_process_subtype_rule_errors_returns_copy():
    service = EligibilityService(db=StubSession())
    details = {
        "passed": ["a"],
        "warnings": ["b"],
        "errors": ["c"],
    }

    processed = service._process_subtype_rule_errors(details)

    assert processed == details
    assert processed is not details


def test_get_nested_field_value_variants():
    service = EligibilityService(db=StubSession())
    data = {"a": {"b": {"c": 42}}, "x": "value"}

    assert service._get_nested_field_value(data, "x") == "value"
    assert service._get_nested_field_value(data, "a.b.c") == 42
    assert service._get_nested_field_value(data, "a.b.z") == ""


def test_evaluate_rule_operators():
    service = EligibilityService(db=StubSession())
    student = {"num": "5", "tags": "alpha", "text": "hello world"}

    assert service._evaluate_rule(student, build_rule(condition_field="num", operator=">=", expected_value="4"))
    assert service._evaluate_rule(student, build_rule(condition_field="num", operator="!=", expected_value="3"))
    assert service._evaluate_rule(
        student, build_rule(condition_field="tags", operator="in", expected_value="alpha,gamma")
    )
    assert service._evaluate_rule(
        student, build_rule(condition_field="text", operator="contains", expected_value="world")
    )
    assert service._evaluate_rule(
        student, build_rule(condition_field="text", operator="not_contains", expected_value="zzz")
    )
    assert service._evaluate_rule(student, build_rule(condition_field="num", operator="not_in", expected_value="1,2"))
    assert service._evaluate_rule(student, build_rule(condition_field="num", operator="<", expected_value="6"))
    assert service._evaluate_rule(student, build_rule(condition_field="num", operator=">", expected_value="4"))

    # Unknown operator returns False
    assert (
        service._evaluate_rule(student, build_rule(condition_field="num", operator="??", expected_value="5")) is False
    )


@pytest.mark.asyncio
async def test_determine_required_student_api_type():
    rule_basic = build_rule(rule_type="student")
    rule_term = build_rule(rule_type="student_term")
    config = build_config()

    session = StubSession([StubResult(scalars=[rule_basic]), StubResult(scalars=[rule_term])])
    service = EligibilityService(db=session)

    result_basic = await service.determine_required_student_api_type(config)
    result_term = await service.determine_required_student_api_type(config)

    assert result_basic == "student"
    assert result_term == "student_term"


@pytest.mark.asyncio
async def test_get_application_status(monkeypatch):
    config = build_config()

    empty_session = StubSession([StubResult(scalar=None)])
    service = EligibilityService(db=empty_session)
    status = await service.get_application_status(user_id=1, config=config)

    assert status["has_application"] is False
    assert status["can_apply"] is True

    submitted_app = SimpleNamespace(
        id=99,
        status=ApplicationStatus.SUBMITTED.value,
        scholarship_type_id=config.scholarship_type_id,
        academic_year=config.academic_year,
    )
    filled_session = StubSession([StubResult(scalar=submitted_app)])
    service.db = filled_session

    status_existing = await service.get_application_status(user_id=1, config=config)

    assert status_existing["has_application"] is True
    assert status_existing["application_id"] == 99
    assert status_existing["status_display"] == "已申請"
    assert status_existing["can_apply"] is False


@pytest.mark.asyncio
async def test_check_existing_applications(monkeypatch):
    config = build_config()
    session = StubSession(
        [StubResult(scalar=None), StubResult(scalar=SimpleNamespace(status=ApplicationStatus.SUBMITTED.value))]
    )
    service = EligibilityService(db=session)

    no_existing = await service._check_existing_applications(1, config, {})
    assert no_existing is True

    existing = await service._check_existing_applications(1, config, {})
    assert existing is False
