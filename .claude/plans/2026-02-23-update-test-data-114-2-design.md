# Design: Update Test Data to 114-2 (2026-02-23)

## Overview

Update all test/seed data to reflect the current academic period: **民國114年第二學期 (114-2)**, corresponding to February 2026.

## Approach

Approach A — Minimal surgical update. Add missing 114-2 term records and update hardcoded academic year/semester references. No structural refactoring.

## Changes

### 1. mock-student-api/main.py — Add 114-2 term records to SAMPLE_TERMS

For each student ending at `trm_year: 114, trm_term: 1`, append a new entry with `trm_term: 2` and `trm_termcount: N+1`. Copy all other fields from the student's 114-1 record with small GPA variations.

Students to update (18 total):

| Student | Dept | Degree | New termcount |
|---|---|---|---|
| `312551007` | 資科工碩 | 碩(2) | 6 |
| `312551183` | 資科工博 | 博(1) | 4 |
| `412551012` | 資科工博 | 博(1) | 6 |
| `412551010` | 資科工博 | 博(1) | 6 |
| `stu_under` | 電機資訊學士班 | 學(3) | 6 |
| `stu_phd` | 電機工程博士班 | 博(1) | 6 |
| `stu_master` | 電機工程碩士班 | 碩(2) | 6 |
| `stu_direct` | 電機工程博士班 | 博(1) | 3 |
| `phd_china` | 電機工程博士班 | 博(1) | 6 |
| `313612215` | 電機資訊學士班 | 學(3) | 4 |
| `cs_phd001` | 資工系 | 博(1) | 6 |
| `cs_phd002` | 資工系 | 博(1) | 8 |
| `cs_phd003` | 資工系 | 博(1) | 10 |
| `cs_phd_intl` | 資工系 | 博(1) | 4 |
| `ee_phd003` | 電機系 | 博(1) | 10 |
| `ee_phd_exchange` | 電機系 | 博(1) | 3 |
| `me_phd001` | 機械系 | 博(1) | 6 |
| `me_phd002` | 機械系 | 博(1) | 8 |
| `me_phd_robotics` | 機械系 | 博(1) | 4 |

Already have 114-2 (no change): `ee_phd001`, `ee_phd002`, `me_phd003`

### 2. backend/app/seed.py — Professor-student relationships

Update both relationship records:
- `academic_year: 113` → `academic_year: 114`
- `semester: "first"` → `semester: "second"`

### 3. backend/app/db/seed_scholarship_configs.py — Add 114-2 scholarship config

Add `undergraduate_freshman_114_2` alongside the existing `undergraduate_freshman_114_1`:
- `config_code`: `undergraduate_freshman_114_2`
- `config_name`: `學士班新生獎學金 114學年第二學期`
- `semester`: `Semester.second`
- Date offsets: same pattern as 114-1 (relative to `now`)

## Out of Scope

- `std_termcount` in `SAMPLE_STUDENTS` (basic student info) — intentionally not updated (Approach A)
- Scholarship rules (`academic_year: 114` — already correct)
- Scholarship configs for phd/direct_phd (yearly, not semester-based)
- Dynamic refactoring of `SAMPLE_TERMS`
