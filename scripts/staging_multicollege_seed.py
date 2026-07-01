"""
Staging mock seed — N colleges x M students, PhD applications submitted and
pending COLLEGE review (待學院審核), with COMPLETE application data.

Why this exists
---------------
Staging (ss.test.nycu.edu.tw / docker-compose.staging.yml) has NO mock SIS API —
the backend talks to the real NYCU SIS — and its seed runs in production mode
(admin + configs only). So we build the full student_data INLINE and insert
straight into the DB.

What "complete" covers here
---------------------------
STORED data (this script fills it fully):
  * student_data  = full SIS shape: all API-1 (std_*/com_*/mgd_title/ToDoctor)
                    + 4 metadata (_api_*) + API-2 (trm_*, incl. GPA/ranking).
  * submitted_form_data.fields = the two real PhD fields: master_school_info,
                    contact_phone  (documents = []; no required PhD docs exist).
  * user_profiles = account_number (→ 匯款帳號 col) + advisor_* (→ 指導教授 col).
These make the 申請清單 table and the 申請總表匯出 (彙整表) look complete.

HARD LIMIT (cannot be fixed by seeding on real staging):
  The 審核詳情 dialog's 基本資訊/學籍/GPA tabs call
  GET /college-review/students/{id}/preview -> StudentService.get_student_basic_info
  -> LIVE SIS. For a fake 學號 the real SIS returns 404, so those panels stay
  blank no matter what student_data we store. To fill them you need real NYCU
  student numbers (real PII) or a mock SIS pointed at by STUDENT_API_BASE_URL.

College 待審核 visibility (verified): status='submitted' AND
student_data->>'std_academyno' == reviewer users.college_code. No time gate.

Run — pipe the script into the running backend container (also works on dev,
which HAS a mock SIS, but the fake 學號 still aren't in its SAMPLE_STUDENTS so the
學生資訊 preview tab is blank there too):
  # staging
  docker exec -i scholarship_backend_staging python - < scripts/staging_multicollege_seed.py
  # dev
  docker compose -f docker-compose.dev.yml exec -T backend python - < scripts/staging_multicollege_seed.py

Idempotent: wipes its own STG-MOCK-% apps + stgmock_* users first. Env overrides:
  PER_COLLEGE=20  COLLEGES=A,B,C,E  YEAR=114  OPEN_REVIEW_WINDOW=0
Set OPEN_REVIEW_WINDOW=1 only if you also want to create/finalize a college
ranking today (that path IS deadline-gated on the config's college_review_end).
"""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.db.session import AsyncSessionLocal

# best-effort PII encryption for std_pid (raw-SQL INSERT bypasses the ORM TypeDecorator)
try:
    from app.core.pii_crypto import encrypt_pii_idempotent
except Exception:  # pragma: no cover - name/path drift guard
    encrypt_pii_idempotent = None

# ---- scenario config (override via env) ------------------------------------
YEAR = int(os.environ.get("YEAR", "114"))
PER_COLLEGE = int(os.environ.get("PER_COLLEGE", "20"))
OPEN_WINDOW = os.environ.get("OPEN_REVIEW_WINDOW", "0") == "1"
SUBTYPES = ["nstc", "moe_1w"]  # must exist in the phd config's quotas

# academy code -> (reviewer nycu_id, reviewer name, college name, dept code, dept name)
# dept code MUST match a real departments.code or the 總表匯出 groups the app under 未知.
COLLEGE_DEFS = {
    "A": ("stgmock_college_a", "人文社會學院審核員(mock)", "人文社會學院", "4460", "教育研究所博士班"),
    "B": ("stgmock_college_b", "生物科技學院審核員(mock)", "生物科技學院", "184", "生醫科學與工程博士學位學程"),
    "C": ("stgmock_college_c", "資訊學院審核員(mock)", "資訊學院", "3551", "資訊科學與工程研究所博士班"),
    "E": ("stgmock_college_e", "電機學院審核員(mock)", "電機學院", "1511", "電子研究所博士班"),
}
_codes = [c.strip().upper() for c in os.environ.get("COLLEGES", "A,B,C,E").split(",") if c.strip()]
COLLEGES = {c: COLLEGE_DEFS[c] for c in _codes if c in COLLEGE_DEFS}
if not COLLEGES:
    raise SystemExit(f"No known colleges among {_codes}; valid: {list(COLLEGE_DEFS)}")

APP_PREFIX = f"STG-MOCK-{YEAR}-"
USER_PREFIX = "stgmock_"
_pii_warned = [False]


def say(msg):
    print(msg, flush=True)


def enc_pid(pid):
    """Encrypt std_pid like the real write path; fall back to plaintext if the
    key isn't available (reads still work — read path checks the pii: prefix)."""
    if not pid or encrypt_pii_idempotent is None:
        return pid
    try:
        return encrypt_pii_idempotent(pid)
    except Exception as e:
        if not _pii_warned[0]:
            say(f"   WARN: PII encrypt unavailable ({e}); storing std_pid as plaintext")
            _pii_warned[0] = True
        return pid


def snapshot(code, depno, depname, k, seq):
    """Full SIS-shaped student_data (API-1 + metadata + API-2). Values vary per
    student; eligibility fields chosen to pass PhD hard/warning rules; std_pid
    encrypted; std_academyno carries the college code the reviewer filters on."""
    now = datetime.now(timezone.utc)
    stdcode = f"{YEAR - 3}{depno}{k:02d}"  # e.g. 111 + 4460 + 01
    cname = f"{COLLEGE_DEFS[code][2]}測試生{k:02d}"
    gpa = round(4.0 - (k - 1) * 0.03, 2)  # 4.00 downwards → stable rank order
    termcount = 3  # within 1-6 (moe rule) and PhD range
    snap = {
        # --- API 1: ScholarshipStudent (basic info) ---
        "std_stdcode": stdcode,
        "std_enrollyear": YEAR - 3,
        "std_enrollterm": 1,
        "std_highestschname": "國立陽明交通大學",
        "std_cname": cname,
        "std_ename": f"MOCK STUDENT {code}{k:02d}",
        "std_pid": enc_pid(f"A2{seq:08d}"),
        "std_bdate": "880515",
        "std_academyno": code,  # <-- load-bearing: matched to reviewer.college_code
        "std_depno": depno,  # <-- must match departments.code for export grouping
        "std_sex": 1 if k % 2 else 2,
        "std_nation": "中華民國",
        "std_degree": 1,  # 博士生 (hard rule)
        "std_enrolltype": 1,  # 一般入學管道 (avoids 2/5/6/7 warning)
        "std_identity": 1,  # 非陸港澳、非僑外
        "std_schoolid": 1,  # 一般生
        "std_overseaplace": "",
        "std_termcount": termcount,
        "std_studingstatus": 1,  # 在學 (note SIS spelling)
        "mgd_title": "在學",
        "ToDoctor": 0,
        "com_commadd": "新竹市東區大學路1001號",
        "com_email": f"{USER_PREFIX}{code.lower()}{k:02d}@stg.mock.nycu.edu.tw",
        "com_cellphone": f"09{seq % 100000000:08d}",
        # --- internal metadata (4 keys, like get_student_snapshot) ---
        "_api_fetched_at": now.isoformat(),
        "_api_source": "staging-mock-seed",
        "_term_data_status": "success",
        "_term_error_message": None,
        # --- API 2: ScholarshipStudentTerm (term data) ---
        "trm_year": YEAR,
        "trm_term": 1,
        "trm_termcount": termcount,
        "trm_studystatus": 1,
        "trm_degree": 1,
        "trm_academyno": code,
        "trm_academyname": COLLEGE_DEFS[code][2],
        "trm_depno": depno,
        "trm_depname": depname,
        "trm_placings": 0,  # PhD students aren't class-ranked
        "trm_placingsrate": 0.0,
        "trm_depplacing": 0,
        "trm_depplacingrate": 0.0,
        "trm_ascore_gpa": gpa,
    }
    return snap, stdcode, cname


def form(cname, phone):
    """submitted_form_data with the two real PhD dynamic fields (documents: [])."""

    def f(fid, v):
        return {"field_id": fid, "field_type": "text", "value": v, "required": True, "validation_rules": None}

    return {
        "fields": {
            "master_school_info": f("master_school_info", f"國立陽明交通大學{cname[:2]}碩士班"),
            "contact_phone": f("contact_phone", phone),
        },
        "documents": [],
    }


async def resolve_scholarship(db):
    stype = (await db.execute(text("SELECT id FROM scholarship_types WHERE code='phd'"))).scalar()
    if stype is None:
        raise SystemExit("PhD scholarship_type (code='phd') not found — run `python -m app.seed` first.")
    row = (
        await db.execute(
            text("""SELECT id, config_name, amount, is_active
                   FROM scholarship_configurations
                   WHERE scholarship_type_id=:t AND academic_year=:y
                   ORDER BY is_active DESC, id DESC LIMIT 1"""),
            {"t": stype, "y": YEAR},
        )
    ).first()
    if row is None:
        raise SystemExit(f"No PhD scholarship_configuration for academic_year={YEAR}.")
    cfg_id, cfg_name, amount, is_active = row
    if not is_active:
        say(f"   WARNING: config id={cfg_id} for {YEAR} is is_active=FALSE — college UI year filter may 403.")
    say(f"   scholarship: phd type={stype}  config={cfg_id} ({cfg_name})  amount={amount}  active={is_active}")
    return stype, cfg_id, int(amount or 40000)


async def check_departments(db):
    codes = [d[3] for d in COLLEGES.values()]
    found = {
        r[0] for r in (await db.execute(text("SELECT code FROM departments WHERE code = ANY(:c)"), {"c": codes})).all()
    }
    missing = [c for c in codes if c not in found]
    if missing:
        say(f"   WARNING: dept codes not in departments table: {missing} — 總表匯出 will group these under 未知.")
    else:
        say(f"   dept codes OK in departments: {codes}")


async def cleanup(db):
    appids = [
        r[0] for r in (await db.execute(text(f"SELECT id FROM applications WHERE app_id LIKE '{APP_PREFIX}%'"))).all()
    ]
    if appids:
        await db.execute(
            text(
                "DELETE FROM application_review_items WHERE review_id IN "
                "(SELECT id FROM application_reviews WHERE application_id = ANY(:i))"
            ),
            {"i": appids},
        )
        await db.execute(text("DELETE FROM application_reviews WHERE application_id = ANY(:i)"), {"i": appids})
        await db.execute(text("DELETE FROM college_ranking_items WHERE application_id = ANY(:i)"), {"i": appids})
        await db.execute(text("DELETE FROM applications WHERE id = ANY(:i)"), {"i": appids})
    uids = [r[0] for r in (await db.execute(text(f"SELECT id FROM users WHERE nycu_id LIKE '{USER_PREFIX}%'"))).all()]
    if uids:
        await db.execute(text("DELETE FROM admin_scholarships WHERE admin_id = ANY(:i)"), {"i": uids})
        await db.execute(text("DELETE FROM user_profiles WHERE user_id = ANY(:i)"), {"i": uids})
        await db.execute(text("DELETE FROM users WHERE id = ANY(:i)"), {"i": uids})
    say(f"   cleaned prior: {len(appids)} apps, {len(uids)} users")


async def ensure_professor(db):
    uid = (await db.execute(text("SELECT id FROM users WHERE nycu_id='stgmock_prof'"))).scalar()
    if uid is None:
        uid = (
            await db.execute(text("""INSERT INTO users (nycu_id,name,email,user_type,status,role,created_at,updated_at)
                       VALUES ('stgmock_prof','Mock 指導教授','stgmock_prof@stg.mock.nycu.edu.tw',
                               'employee','在職','professor',NOW(),NOW()) RETURNING id"""))
        ).scalar()
    return uid


async def ensure_reviewer(db, code, nyid, name, stype):
    uid = (await db.execute(text("SELECT id FROM users WHERE nycu_id=:n"), {"n": nyid})).scalar()
    if uid is None:
        uid = (
            await db.execute(
                text("""INSERT INTO users (nycu_id,name,email,user_type,status,college_code,role,created_at,updated_at)
                       VALUES (:n,:name,:email,'employee','在職',:cc,'college',NOW(),NOW()) RETURNING id"""),
                {"n": nyid, "name": name, "email": f"{nyid}@stg.mock.nycu.edu.tw", "cc": code},
            )
        ).scalar()
    else:
        await db.execute(
            text("UPDATE users SET college_code=:cc, role='college' WHERE id=:id"), {"cc": code, "id": uid}
        )
    # link so the college UI year/type filter doesn't 403
    await db.execute(
        text("""INSERT INTO admin_scholarships (admin_id,scholarship_id,assigned_at)
               VALUES (:a,:s,NOW()) ON CONFLICT ON CONSTRAINT uq_admin_scholarship DO NOTHING"""),
        {"a": uid, "s": stype},
    )
    return uid


async def maybe_open_window(db, cfg_id):
    if not OPEN_WINDOW:
        return
    now = datetime.now(timezone.utc)
    await db.execute(
        text("""UPDATE scholarship_configurations
               SET professor_review_start=:ps, professor_review_end=:pe,
                   college_review_start=:cs, college_review_end=:ce, review_deadline=:ce
               WHERE id=:id"""),
        {
            "id": cfg_id,
            "ps": now - timedelta(days=7),
            "pe": now + timedelta(days=90),
            "cs": now - timedelta(days=7),
            "ce": now + timedelta(days=90),
        },
    )
    say(f"   OPEN_REVIEW_WINDOW: config {cfg_id} review windows extended to now+90d")


async def main():
    async with AsyncSessionLocal() as db:
        say(
            f"── staging mock seed: {list(COLLEGES)} x {PER_COLLEGE} = {len(COLLEGES) * PER_COLLEGE} apps, year {YEAR} ──"
        )
        stype, cfg_id, amount = await resolve_scholarship(db)
        await check_departments(db)
        await cleanup(db)
        await maybe_open_window(db, cfg_id)
        prof_id = await ensure_professor(db)
        sname = f"博士生獎學金 {YEAR}學年"
        subtypes_json = json.dumps(SUBTYPES)

        seq = 0
        for code, (nyid, rname, cname_college, depno, depname) in COLLEGES.items():
            reviewer_id = await ensure_reviewer(db, code, nyid, rname, stype)
            for k in range(1, PER_COLLEGE + 1):
                seq += 1
                snap, stdcode, sname_student = snapshot(code, depno, depname, k, seq)
                phone = f"09{seq % 100000000:08d}"
                # student user
                suid = (
                    await db.execute(
                        text(
                            """INSERT INTO users (nycu_id,name,email,user_type,status,dept_code,dept_name,college_code,role,created_at,updated_at)
                               VALUES (:n,:name,:email,'student','在學',:dc,:dn,:cc,'student',NOW(),NOW()) RETURNING id"""
                        ),
                        {
                            "n": f"{USER_PREFIX}{code.lower()}{k:02d}",
                            "name": sname_student,
                            "email": snap["com_email"],
                            "dc": depno,
                            "dn": depname,
                            "cc": code,
                        },
                    )
                ).scalar()
                # user_profile → feeds 匯款帳號 / 指導教授 export columns
                await db.execute(
                    text(
                        """INSERT INTO user_profiles (user_id,account_number,advisor_name,advisor_email,advisor_nycu_id,created_at,updated_at)
                           VALUES (:u,:acct,'Mock 指導教授','stgmock_prof@stg.mock.nycu.edu.tw','stgmock_prof',NOW(),NOW())
                           ON CONFLICT (user_id) DO NOTHING"""
                    ),
                    {"u": suid, "acct": f"700{seq:07d}"},
                )
                # application (submitted, pending college review)
                aid = (
                    await db.execute(
                        text("""INSERT INTO applications
                               (app_id,user_id,scholarship_type_id,scholarship_configuration_id,scholarship_name,amount,
                                scholarship_subtype_list,sub_type_selection_mode,sub_scholarship_type,is_renewal,
                                status,status_name,review_stage,academic_year,semester,student_data,submitted_form_data,
                                quota_allocation_status,submitted_at,agree_terms,created_at,updated_at)
                               VALUES
                               (:app_id,:uid,:stype,:cfg,:sname,:amount,
                                CAST(:subtypes AS json),'multiple','nstc',false,
                                'submitted','已提交','college_review',:year,NULL,CAST(:sd AS jsonb),CAST(:fd AS jsonb),
                                NULL,NOW(),true,NOW(),NOW()) RETURNING id"""),
                        {
                            "app_id": f"{APP_PREFIX}{seq:05d}",
                            "uid": suid,
                            "stype": stype,
                            "cfg": cfg_id,
                            "sname": sname,
                            "amount": amount,
                            "subtypes": subtypes_json,
                            "year": YEAR,
                            "sd": json.dumps(snap, ensure_ascii=False),
                            "fd": json.dumps(form(sname_student, phone), ensure_ascii=False),
                        },
                    )
                ).scalar()
                # professor approve → reads as 待學院審核 (not 教授審核中) + per-sub-type approvals for distribution
                rid = (
                    await db.execute(
                        text(
                            """INSERT INTO application_reviews (application_id, reviewer_id, recommendation, comments, reviewed_at, created_at)
                               VALUES (:a,:p,'approve','staging mock seed',NOW(),NOW()) RETURNING id"""
                        ),
                        {"a": aid, "p": prof_id},
                    )
                ).scalar()
                await db.execute(
                    text("""INSERT INTO application_review_items (review_id, sub_type_code, recommendation, comments)
                           VALUES (:r,'nstc','approve',NULL),(:r,'moe_1w','approve',NULL)"""),
                    {"r": rid},
                )
            say(f"   college {code}: reviewer={reviewer_id} ({nyid}), {PER_COLLEGE} apps")
        await db.commit()

        rows = (await db.execute(text(f"""SELECT student_data->>'std_academyno' AS college, count(*)
                        FROM applications
                        WHERE app_id LIKE '{APP_PREFIX}%' AND status='submitted'
                        GROUP BY 1 ORDER BY 1"""))).all()
        say("── verify: 待審核 apps per college ──")
        for c, n in rows:
            say(f"   {c}: {n}")
        total = sum(n for _, n in rows)
        say(f"RESULT: seeded {total} submitted apps across {len(rows)} colleges (app_id prefix {APP_PREFIX})")
        say("NOTE: 清單 + 總表匯出 = 完整; 審核詳情 dialog 基本資訊/GPA 讀即時 SIS → 假學號會空白 (見檔頭說明)")


if __name__ == "__main__":
    asyncio.run(main())
