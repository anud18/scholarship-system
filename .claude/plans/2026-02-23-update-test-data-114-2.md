# Update Test Data to 114-2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update all test/seed data to reflect 民國114年第二學期 (114-2), the current semester as of 2026-02-23.

**Architecture:** Three files receive purely data-level changes — no logic modifications. Mock API gets new term records appended; seed files get updated year/semester values. The scholarship configs use dynamic `now`-relative dates already, so only the config entry itself is added.

**Tech Stack:** Python (FastAPI mock, SQLAlchemy seed), in-memory dicts

---

### Task 1: Add 114-2 term records to mock-student-api/main.py

**Files:**
- Modify: `mock-student-api/main.py` (SAMPLE_TERMS dict, lines ~652–2655)

No automated tests exist for this file. Verification is manual (see Step 3).

**Step 1: Add 114-2 entries to SAMPLE_TERMS**

In `mock-student-api/main.py`, for each student listed below, add the following entry **at the beginning** of its list (newest-first ordering matches existing pattern for some students, but appending to end is also fine — the API filters by year+term regardless). Place each new block immediately **after** the closing `},` of that student's 114-1 entry.

```python
# 312551007 — after existing trm_year=114 trm_term=1 entry (trm_termcount=5)
        {
            "std_stdcode": "312551007",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 6,
            "trm_studystatus": 1,
            "trm_degree": 2,
            "trm_academyno": "C",
            "trm_academyname": "資訊學院",
            "trm_depno": "3551",
            "trm_depname": "資科工碩",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 3.88,
        },
```

```python
# 312551183 — after existing trm_year=114 trm_term=1 entry (trm_termcount=3)
        {
            "std_stdcode": "312551183",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 4,
            "trm_studystatus": 1,
            "trm_degree": 1,
            "trm_academyno": "C",
            "trm_academyname": "資訊學院",
            "trm_depno": "4551",
            "trm_depname": "資科工博",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 0.0,
        },
```

```python
# 412551012 — after existing trm_year=114 trm_term=1 entry (trm_termcount=5)
        {
            "std_stdcode": "412551012",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 6,
            "trm_studystatus": 1,
            "trm_degree": 1,
            "trm_academyno": "C",
            "trm_academyname": "資訊學院",
            "trm_depno": "4551",
            "trm_depname": "資科工博",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 0.0,
        },
```

```python
# 412551010 — after existing trm_year=114 trm_term=1 entry (trm_termcount=5)
        {
            "std_stdcode": "412551010",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 6,
            "trm_studystatus": 1,
            "trm_degree": 1,
            "trm_academyno": "C",
            "trm_academyname": "資訊學院",
            "trm_depno": "4551",
            "trm_depname": "資科工博",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 0.0,
        },
```

```python
# stu_under — after existing trm_year=114 trm_term=1 entry (trm_termcount=5)
        {
            "std_stdcode": "stu_under",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 6,
            "trm_studystatus": 1,
            "trm_degree": 3,
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機資訊學士班",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 3.62,
        },
```

```python
# stu_phd — after existing trm_year=114 trm_term=1 entry (trm_termcount=5)
        {
            "std_stdcode": "stu_phd",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 6,
            "trm_studystatus": 1,
            "trm_degree": 1,
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系博士班",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 4.18,
        },
```

```python
# stu_master — after existing trm_year=114 trm_term=1 entry (trm_termcount=5)
        {
            "std_stdcode": "stu_master",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 6,
            "trm_studystatus": 1,
            "trm_degree": 2,
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系碩士班",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 3.82,
        },
```

```python
# stu_direct — after existing trm_year=114 trm_term=1 entry (trm_termcount=2)
        {
            "std_stdcode": "stu_direct",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 3,
            "trm_studystatus": 1,
            "trm_degree": 1,
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系博士班",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 4.08,
        },
```

```python
# phd_china — after existing trm_year=114 trm_term=1 entry (trm_termcount=5)
        {
            "std_stdcode": "phd_china",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 6,
            "trm_studystatus": 1,
            "trm_degree": 1,
            "trm_academyno": "EE",
            "trm_academyname": "電機學院",
            "trm_depno": "3551",
            "trm_depname": "電機工程學系博士班",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 3.92,
        },
```

```python
# 313612215 — after existing trm_year=114 trm_term=1 entry (trm_termcount=3)
        {
            "std_stdcode": "313612215",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 4,
            "trm_studystatus": 1,
            "trm_degree": 3,
            "trm_academyno": "I",
            "trm_academyname": "智慧科學暨綠能學院",
            "trm_depno": "EECS01",
            "trm_depname": "電機資訊學士班",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 3.88,
        },
```

```python
# cs_phd001 — after existing trm_year=114 trm_term=1 entry (trm_termcount=5)
        {
            "std_stdcode": "cs_phd001",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 6,
            "trm_studystatus": 1,
            "trm_degree": 1,
            "trm_academyno": "C",
            "trm_academyname": "資訊學院",
            "trm_depno": "CS",
            "trm_depname": "資工系",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 3.98,
        },
```

```python
# cs_phd002 — after existing trm_year=114 trm_term=1 entry (trm_termcount=7)
        {
            "std_stdcode": "cs_phd002",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 8,
            "trm_studystatus": 1,
            "trm_degree": 1,
            "trm_academyno": "C",
            "trm_academyname": "資訊學院",
            "trm_depno": "CS",
            "trm_depname": "資工系",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 4.02,
        },
```

```python
# cs_phd003 — after existing trm_year=114 trm_term=1 entry (trm_termcount=9)
        {
            "std_stdcode": "cs_phd003",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 10,
            "trm_studystatus": 1,
            "trm_degree": 1,
            "trm_academyno": "C",
            "trm_academyname": "資訊學院",
            "trm_depno": "CS",
            "trm_depname": "資工系",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 4.08,
        },
```

```python
# cs_phd_intl — after existing trm_year=114 trm_term=1 entry (trm_termcount=3)
        {
            "std_stdcode": "cs_phd_intl",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 4,
            "trm_studystatus": 1,
            "trm_degree": 1,
            "trm_academyno": "C",
            "trm_academyname": "資訊學院",
            "trm_depno": "CS",
            "trm_depname": "資工系",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 4.08,
        },
```

```python
# ee_phd003 — after existing trm_year=114 trm_term=1 entry (trm_termcount=9)
        {
            "std_stdcode": "ee_phd003",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 10,
            "trm_studystatus": 1,
            "trm_degree": 1,
            "trm_academyno": "E",
            "trm_academyname": "電機學院",
            "trm_depno": "EE",
            "trm_depname": "電機系",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 4.12,
        },
```

```python
# ee_phd_exchange — after existing trm_year=114 trm_term=1 entry (trm_termcount=2)
        {
            "std_stdcode": "ee_phd_exchange",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 3,
            "trm_studystatus": 1,
            "trm_degree": 1,
            "trm_academyno": "E",
            "trm_academyname": "電機學院",
            "trm_depno": "EE",
            "trm_depname": "電機系",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 4.22,
        },
```

```python
# me_phd001 — after existing trm_year=114 trm_term=1 entry (trm_termcount=5)
        {
            "std_stdcode": "me_phd001",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 6,
            "trm_studystatus": 1,
            "trm_degree": 1,
            "trm_academyno": "M",
            "trm_academyname": "機械學院",
            "trm_depno": "ME",
            "trm_depname": "機械系",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 4.02,
        },
```

```python
# me_phd002 — after existing trm_year=114 trm_term=1 entry (trm_termcount=7)
        {
            "std_stdcode": "me_phd002",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 8,
            "trm_studystatus": 1,
            "trm_degree": 1,
            "trm_academyno": "M",
            "trm_academyname": "機械學院",
            "trm_depno": "ME",
            "trm_depname": "機械系",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 4.18,
        },
```

```python
# me_phd_robotics — after existing trm_year=114 trm_term=1 entry (trm_termcount=3)
        {
            "std_stdcode": "me_phd_robotics",
            "trm_year": 114,
            "trm_term": 2,
            "trm_termcount": 4,
            "trm_studystatus": 1,
            "trm_degree": 1,
            "trm_academyno": "M",
            "trm_academyname": "機械學院",
            "trm_depno": "ME",
            "trm_depname": "機械系",
            "trm_placings": 0,
            "trm_placingsrate": 0.0,
            "trm_depplacing": 0,
            "trm_depplacingrate": 0.0,
            "trm_ascore_gpa": 4.18,
        },
```

**Step 2: Verify syntax is valid**

```bash
cd mock-student-api && python -c "import main; print('OK:', len(main.SAMPLE_TERMS), 'students')"
```

Expected: `OK: <N> students` with no errors.

Also spot-check one student has 114-2:

```bash
python -c "
import main
terms_312 = [t for t in main.SAMPLE_TERMS['312551007'] if t['trm_year']==114 and t['trm_term']==2]
print('312551007 114-2:', terms_312)
"
```

Expected: one dict printed with `trm_termcount: 6`.

**Step 3: Commit**

```bash
git add mock-student-api/main.py
git commit -m "chore(test-data): add 114-2 term records to mock student API"
```

---

### Task 2: Update professor-student relationships in backend/app/seed.py

**Files:**
- Modify: `backend/app/seed.py` (function `seed_professor_student_relationships`, lines ~286–315)

**Step 1: Update both relationship records**

Find the two entries in the `relationships` list inside `seed_professor_student_relationships`. Change:

```python
# BEFORE (both records)
"academic_year": 113,
"semester": "first",

# AFTER (both records)
"academic_year": 114,
"semester": "second",
```

There are exactly two dicts in the list — update both.

**Step 2: Verify**

```bash
grep -n "academic_year\|semester" backend/app/seed.py | grep -A1 "113\|first"
```

Expected: no matches (both changed).

**Step 3: Commit**

```bash
git add backend/app/seed.py
git commit -m "chore(test-data): update professor-student relationships to 114-2"
```

---

### Task 3: Add undergraduate_freshman_114_2 scholarship config

**Files:**
- Modify: `backend/app/db/seed_scholarship_configs.py` (function `seed_scholarship_configurations`, `configurations_data` list, ~line 50)

**Step 1: Add new config entry**

In `seed_scholarship_configs.py`, inside the `configurations_data` list in `seed_scholarship_configurations()`, add after the existing `undergraduate_freshman_114_1` entry:

```python
        # 學士班新生獎學金配置 (114-2)
        {
            "scholarship_type_id": undergrad_scholarship.id,
            "config_code": "undergraduate_freshman_114_2",
            "config_name": "學士班新生獎學金 114學年第二學期",
            "academic_year": 114,
            "semester": Semester.second,
            "description": "114學年度第二學期學士班新生獎學金配置",
            "description_en": "Undergraduate Freshman Scholarship Configuration for 114-2",
            "has_quota_limit": False,
            "has_college_quota": False,
            "quota_management_mode": QuotaManagementMode.simple,
            "total_quota": 50,
            "amount": 10000,
            "currency": "TWD",
            "application_start_date": now - timedelta(days=30),
            "application_end_date": now + timedelta(days=30),
            "is_active": True,
            "effective_start_date": now - timedelta(days=60),
            "effective_end_date": now + timedelta(days=90),
            "version": "1.0",
        },
```

**Step 2: Verify import — Semester.second must be valid**

```bash
cd backend && python -c "from app.models.enums import Semester; print(Semester.second)"
```

Expected: `Semester.second`

**Step 3: Commit**

```bash
git add backend/app/db/seed_scholarship_configs.py
git commit -m "chore(test-data): add undergraduate_freshman_114_2 scholarship config"
```

---

### Task 4: End-to-end verification

**Step 1: Check all three files parse cleanly**

```bash
cd mock-student-api && python -c "import main; print('mock API OK')"
cd backend && python -c "import app.seed; import app.db.seed_scholarship_configs; print('seed OK')"
```

**Step 2: Verify 114-2 term count across all updated students**

```bash
cd mock-student-api && python -c "
import main
students_needing_114_2 = [
    '312551007','312551183','412551012','412551010',
    'stu_under','stu_phd','stu_master','stu_direct','phd_china',
    '313612215','cs_phd001','cs_phd002','cs_phd003','cs_phd_intl',
    'ee_phd003','ee_phd_exchange','me_phd001','me_phd002','me_phd_robotics',
]
missing = []
for s in students_needing_114_2:
    has = any(t['trm_year']==114 and t['trm_term']==2 for t in main.SAMPLE_TERMS.get(s, []))
    if not has:
        missing.append(s)
if missing:
    print('MISSING 114-2:', missing)
else:
    print('All 19 students have 114-2 records')
"
```

Expected: `All 19 students have 114-2 records`
