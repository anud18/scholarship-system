"""
Tests for `app.integrations.nycu_emp.client_mock` mock client.

Wave 6a107 covered the factory + HTTP exceptions; this fills the
remaining mock-client surface. The mock client is the source of
staff data in dev / test / CI — its behavior is load-bearing for:

  - All staff-onboarding test fixtures
  - CI E2E specs that depend on deterministic employee data
  - Local-dev login flows

Wave 6a114 pins:
  - Status filter: "01" returns active only, "02" returns inactive
    only, anything else returns ALL employees
  - Pagination: size=2 per page; ceiling division for total_pages
  - Response wraps data in NYCUEmpPage with status="0000" (success
    sentinel)
  - get_all_employees walks all pages until last (inherited
    behavior from NYCUEmpClientBase)

13 cases.
"""

import pytest

from app.integrations.nycu_emp.client_mock import NYCUEmpMockClient
from app.integrations.nycu_emp.models import NYCUEmpPage

# ─── _get_sample_employees status filtering ──────────────────────────


def test_active_status_returns_three_employees():
    # Pin: status="01" returns the 3 active employees (out of
    # 4 total). Pin so a refactor that drops one breaks the test.
    client = NYCUEmpMockClient()
    active = client._get_sample_employees(status="01")
    assert len(active) == 3
    for emp in active:
        assert emp.employee_status == "01"


def test_inactive_status_returns_one_employee():
    # Pin: status="02" returns the 1 inactive employee.
    client = NYCUEmpMockClient()
    inactive = client._get_sample_employees(status="02")
    assert len(inactive) == 1
    assert inactive[0].employee_status == "02"


def test_unknown_status_returns_all_employees():
    # Pin: anything other than "01" or "02" → ALL 4 employees.
    # Pin so a refactor that defaults to "01" doesn't silently
    # filter out inactive employees from "all" queries.
    client = NYCUEmpMockClient()
    all_emps = client._get_sample_employees(status="anything")
    assert len(all_emps) == 4


def test_default_status_is_active():
    # Pin: default status parameter "01" → active employees only.
    client = NYCUEmpMockClient()
    default_result = client._get_sample_employees()
    explicit_active = client._get_sample_employees(status="01")
    assert len(default_result) == len(explicit_active)


def test_returns_pydantic_models():
    # Pin: results are NYCUEmpItem instances (not raw dicts).
    # Pin so a refactor doesn't break downstream code expecting
    # attribute access (emp.employee_no, etc.).
    from app.integrations.nycu_emp.models import NYCUEmpItem

    client = NYCUEmpMockClient()
    emps = client._get_sample_employees(status="01")
    for emp in emps:
        assert isinstance(emp, NYCUEmpItem)


def test_employee_data_includes_school_email():
    # Pin: every mock employee has school_email populated.
    # Production code branches on this — pin so adding a new
    # mock without school_email doesn't break SSO login fixtures.
    client = NYCUEmpMockClient()
    emps = client._get_sample_employees(status="anything")
    for emp in emps:
        assert emp.school_email
        assert "@" in emp.school_email


# ─── get_employee_page pagination ────────────────────────────────────


@pytest.mark.asyncio
async def test_first_page_returns_two_active_employees():
    # Pin: page_size = 2, page=1 returns first 2 active employees
    # (out of 3 total active).
    client = NYCUEmpMockClient()
    page = await client.get_employee_page(page_row="1", status="01")
    assert isinstance(page, NYCUEmpPage)
    assert len(page.empDataList) == 2


@pytest.mark.asyncio
async def test_second_page_returns_remaining_employee():
    # Pin: page=2 returns the 3rd active employee (only 1 left).
    client = NYCUEmpMockClient()
    page = await client.get_employee_page(page_row="2", status="01")
    assert len(page.empDataList) == 1


@pytest.mark.asyncio
async def test_page_beyond_last_returns_empty():
    # Pin: page=3 (beyond last) returns empty list (not error).
    # Defensive — slice past end of list is harmless in Python.
    client = NYCUEmpMockClient()
    page = await client.get_employee_page(page_row="3", status="01")
    assert page.empDataList == []


@pytest.mark.asyncio
async def test_total_count_reflects_filter():
    # Pin: total_count = filtered count, not base count. Pin so
    # callers can rely on total_count for paginated UI display.
    client = NYCUEmpMockClient()
    active_page = await client.get_employee_page(page_row="1", status="01")
    assert active_page.total_count == 3

    inactive_page = await client.get_employee_page(page_row="1", status="02")
    assert inactive_page.total_count == 1


@pytest.mark.asyncio
async def test_total_pages_uses_ceiling_division():
    # Pin: 3 active / 2 per page = 2 pages (ceiling). Pin so a
    # refactor to integer division would silently drop the last
    # employee (3//2 = 1 page → only 2 employees visible).
    client = NYCUEmpMockClient()
    page = await client.get_employee_page(page_row="1", status="01")
    assert page.total_page == 2


@pytest.mark.asyncio
async def test_response_status_is_success_sentinel():
    # Pin: status="0000" — NYCU API success sentinel. Pin so the
    # mock matches the real API contract (covered in wave 6a107).
    client = NYCUEmpMockClient()
    page = await client.get_employee_page(page_row="1", status="01")
    assert page.status == "0000"
    assert page.is_success is True


# ─── get_all_employees (inherited from base) ─────────────────────────


@pytest.mark.asyncio
async def test_get_all_employees_walks_all_pages():
    # Pin: inherited get_all_employees() returns one entry per
    # page until total_page reached. With 3 active / 2 per page,
    # we get 2 pages.
    client = NYCUEmpMockClient()
    all_pages = await client.get_all_employees(status="01")
    assert len(all_pages) == 2

    # Concatenated employees match the full filtered set
    all_emps = []
    for page in all_pages:
        all_emps.extend(page.empDataList)
    assert len(all_emps) == 3
