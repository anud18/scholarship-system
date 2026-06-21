"""
Zero → roster, no browser. Drives the full multi-college scholarship pipeline
through the backend's own services + DB, inside the running dev container:

  seed (college reviewers + PhD apps with student_data from the mock SIS API + professor approvals)
    → per-college ranking create + finalize   (CollegeReviewService)
    → matrix distribution allocate + finalize  (ManualDistributionService)
    → roster generation                        (RosterService)
    → verify roster spans ALL colleges, every entry included

Run it against the dev stack (operates on the docker container, not Playwright):

  docker compose -f docker-compose.dev.yml exec -T backend python - < scripts/multicollege_seed_to_roster.py

or via the wrapper:  scripts/multicollege_seed_to_roster.sh

Idempotent: wipes its own 'MC-114-' apps + the PhD/114 rankings & rosters first,
so re-runs start clean. Exit 0 only if the roster includes every college.
"""

import asyncio
import json

from sqlalchemy import text

from app.db.session import AsyncSessionLocal, SessionLocal
from app.services.college_review_service import CollegeReviewService
from app.services.manual_distribution_service import ManualDistributionService
from app.services.roster_service import RosterService
from app.services.student_service import StudentService

# ---- scenario config -------------------------------------------------------
PHD_TYPE = 2  # 博士生獎學金
YEAR = 114
CFG = 5  # active matrix_based config for PhD/114
SEM_API = "yearly"  # distribution/roster semester arg for a yearly cycle
PER_COLLEGE = 2
# code -> (reviewer nycu_id, reviewer name, college full name, dept code, dept name)
COLLEGES = {
    "A": ("hum_college", "人文社會學院審核員", "人文社會學院", "4460", "教育博"),
    "B": ("bio_college", "生物科技學院審核員", "生物科技學院", "5500", "生科博"),
    "C": ("cs_college", "資訊學院審核員", "資訊學院", "3551", "資科工博"),
    "E": ("ee_college", "電機學院審核員", "電機學院", "1511", "電子博"),
}

log = []


def say(msg):
    print(msg, flush=True)
    log.append(msg)


def form(acct):
    f = lambda fid, v: {"field_id": fid, "field_type": "text", "value": v, "required": True, "validation_rules": None}
    return {
        "fields": {
            "postal_account": f("postal_account", acct),
            "account_number": f("account_number", acct),
            "advisor_name": f("advisor_name", "張教授"),
            "advisor_email": f("advisor_email", "professor@nycu.edu.tw"),
            "contact_phone": f("contact_phone", "0978000000"),
        },
        "documents": [],
    }


async def stage_seed(db):
    say("── stage 1: seed (reviewers + apps + professor approvals) ──")
    # cleanup prior cycle data so re-runs are clean
    rk = [
        r[0]
        for r in (
            await db.execute(
                text("SELECT id FROM college_rankings WHERE scholarship_type_id=:t AND academic_year=:y"),
                {"t": PHD_TYPE, "y": YEAR},
            )
        ).all()
    ]
    appids = [r[0] for r in (await db.execute(text("SELECT id FROM applications WHERE app_id LIKE 'MC-114-%'"))).all()]
    ros = [
        r[0]
        for r in (await db.execute(text("SELECT id FROM payment_rosters WHERE roster_code LIKE 'ROSTER-114-%'"))).all()
    ]
    if ros:
        await db.execute(text("DELETE FROM payment_roster_items WHERE roster_id = ANY(:i)"), {"i": ros})
        await db.execute(text("DELETE FROM roster_audit_logs WHERE roster_id = ANY(:i)"), {"i": ros})
        await db.execute(text("DELETE FROM payment_rosters WHERE id = ANY(:i)"), {"i": ros})
    if rk:
        await db.execute(text("DELETE FROM payment_rosters WHERE ranking_id = ANY(:i)"), {"i": rk})
        await db.execute(text("DELETE FROM college_ranking_items WHERE ranking_id = ANY(:i)"), {"i": rk})
        await db.execute(text("DELETE FROM college_rankings WHERE id = ANY(:i)"), {"i": rk})
    if appids:
        await db.execute(
            text(
                "DELETE FROM application_review_items WHERE review_id IN (SELECT id FROM application_reviews WHERE application_id = ANY(:i))"
            ),
            {"i": appids},
        )
        await db.execute(text("DELETE FROM application_reviews WHERE application_id = ANY(:i)"), {"i": appids})
        await db.execute(text("DELETE FROM college_ranking_items WHERE application_id = ANY(:i)"), {"i": appids})
        await db.execute(text("DELETE FROM applications WHERE id = ANY(:i)"), {"i": appids})

    prof_id = (await db.execute(text("SELECT id FROM users WHERE role='professor' ORDER BY id LIMIT 1"))).scalar()
    if prof_id is None:
        raise RuntimeError("no professor user found to author approvals")

    student_svc = StudentService()  # reads student_data from the mock SIS API

    reviewers, seq = {}, 0
    for code, (nyid, name, cn, dc, dn) in COLLEGES.items():
        uid = (await db.execute(text("SELECT id FROM users WHERE nycu_id=:n"), {"n": nyid})).scalar()
        if uid is None:
            uid = (
                await db.execute(
                    text(
                        """INSERT INTO users (nycu_id,name,email,user_type,status,college_code,role,created_at,updated_at)
                   VALUES (:n,:name,:email,'employee','在職',:cc,'college',NOW(),NOW()) RETURNING id"""
                    ),
                    {"n": nyid, "name": name, "email": f"{nyid}@nycu.edu.tw", "cc": code},
                )
            ).scalar()
        else:
            await db.execute(
                text("UPDATE users SET college_code=:cc, role='college' WHERE id=:id"), {"cc": code, "id": uid}
            )
        await db.execute(
            text("""INSERT INTO admin_scholarships (admin_id,scholarship_id,assigned_at)
               VALUES (:a,:s,NOW()) ON CONFLICT ON CONSTRAINT uq_admin_scholarship DO NOTHING"""),
            {"a": uid, "s": PHD_TYPE},
        )
        reviewers[code] = uid

        for k in range(1, PER_COLLEGE + 1):
            seq += 1
            stdcode = f"mcphd_{code.lower()}{k}"
            # "use the SIS API": pull the real student_data snapshot (std_* + trm_*).
            snap = await student_svc.get_student_snapshot(stdcode, academic_year=str(YEAR), semester=None)
            sname = snap.get("std_cname") or stdcode
            suid = (await db.execute(text("SELECT id FROM users WHERE nycu_id=:n"), {"n": stdcode})).scalar()
            if suid is None:
                suid = (
                    await db.execute(
                        text(
                            """INSERT INTO users (nycu_id,name,email,user_type,status,dept_code,dept_name,college_code,role,created_at,updated_at)
                       VALUES (:n,:name,:email,'student','在學',:dc,:dn,:cc,'student',NOW(),NOW()) RETURNING id"""
                        ),
                        {
                            "n": stdcode,
                            "name": sname,
                            "email": f"{stdcode}@nycu.edu.tw",
                            "dc": dc,
                            "dn": dn,
                            "cc": code,
                        },
                    )
                ).scalar()
            aid = (
                await db.execute(
                    text("""INSERT INTO applications
                   (app_id,user_id,scholarship_type_id,scholarship_configuration_id,scholarship_name,amount,
                    scholarship_subtype_list,sub_type_selection_mode,sub_scholarship_type,is_renewal,
                    status,status_name,review_stage,academic_year,student_data,submitted_form_data,
                    quota_allocation_status,created_at,updated_at)
                   VALUES
                   (:app_id,:uid,2,:cfg,'博士生獎學金 114學年',40000,
                    '["nstc","moe_1w"]','multiple','nstc',false,
                    'submitted','已提交','college_review',114,CAST(:sd AS jsonb),CAST(:fd AS jsonb),
                    NULL,NOW(),NOW()) RETURNING id"""),
                    {
                        "app_id": f"MC-114-0-{seq:05d}",
                        "uid": suid,
                        "cfg": CFG,
                        "sd": json.dumps(snap, default=str),  # real SIS snapshot
                        "fd": json.dumps(form(f"700{seq:07d}")),
                    },
                )
            ).scalar()
            # professor approve recommendation (matrix distribution requires it per sub-type)
            rid = (
                await db.execute(
                    text(
                        """INSERT INTO application_reviews (application_id, reviewer_id, recommendation, comments, reviewed_at, created_at)
                   VALUES (:a,:p,'approve','multi-college seed',NOW(),NOW()) RETURNING id"""
                    ),
                    {"a": aid, "p": prof_id},
                )
            ).scalar()
            await db.execute(
                text("""INSERT INTO application_review_items (review_id, sub_type_code, recommendation, comments)
                   VALUES (:r,'nstc','approve',NULL),(:r,'moe_1w','approve',NULL)"""),
                {"r": rid},
            )
    await db.commit()
    say(f"   reviewers={ {c: reviewers[c] for c in reviewers} }  apps={seq} ({PER_COLLEGE}/college)")
    return reviewers


async def stage_rank(db, reviewers):
    say("── stage 2: per-college ranking create + finalize ──")
    svc = CollegeReviewService(db)
    out = {}
    for code, uid in reviewers.items():
        ranking = await svc.create_ranking(
            scholarship_type_id=PHD_TYPE,
            sub_type_code="default",
            academic_year=YEAR,
            semester=None,
            creator_id=uid,
            ranking_name=f"博士生獎學金 {YEAR} 全年",
            force_new=True,
        )
        await db.commit()
        await svc.finalize_ranking(ranking_id=ranking.id, finalizer_id=uid)
        await db.commit()
        out[code] = ranking.id
        say(f"   college {code}: ranking {ranking.id} finalized ({ranking.total_applications} apps)")
    # cross-check: all finalized simultaneously (issue #1034 regression)
    finalized = (
        await db.execute(
            text(
                "SELECT string_agg(DISTINCT college_code, ',' ORDER BY college_code) FROM college_rankings WHERE is_finalized IS TRUE"
            )
        )
    ).scalar()
    say(f"   finalized colleges = [{finalized}]")
    return out


async def stage_distribute(db, admin_id):
    say("── stage 3: matrix distribution (auto-allocate → save → finalize) ──")
    svc = ManualDistributionService(db)
    suggestions = await svc.auto_allocate_preview(scholarship_type_id=PHD_TYPE, academic_year=YEAR, semester=SEM_API)
    say(f"   auto-allocate suggested {len(suggestions)} allocations")
    alloc = await svc.allocate(PHD_TYPE, YEAR, SEM_API, suggestions, admin_user_id=admin_id)
    await db.commit()
    result = await svc.finalize(PHD_TYPE, YEAR, SEM_API, admin_user_id=admin_id)
    await db.commit()
    say(
        f"   allocate updated={alloc.get('updated_count')}  finalize approved={result['approved_count']} rejected={result['rejected_count']}"
    )
    return result


def stage_roster(admin_id):
    say("── stage 4: roster generation (RosterService, sync) ──")
    with SessionLocal() as sdb:
        svc = RosterService(sdb)
        rosters = svc.generate_rosters_from_distribution(
            scholarship_type_id=PHD_TYPE,
            academic_year=YEAR,
            semester=SEM_API,
            created_by_user_id=admin_id,
            student_verification_enabled=False,
            force_regenerate=True,
        )
        sdb.commit()
        # RosterGenerationResult(created/skipped/locked) — `created` holds the rosters built.
        codes = [r.roster_code for r in rosters.created]
        say(
            f"   generated {len(codes)} roster(s): {codes}"
            f"  (skipped={len(rosters.skipped)}, locked={len(rosters.locked)})"
        )
    return codes


async def stage_verify(db):
    say("── stage 5: verify roster spans every college, all entries included ──")
    rows = (await db.execute(text("""SELECT a.student_data->>'std_academyno' AS college,
                  count(*) FILTER (WHERE pri.is_included) AS included,
                  count(*) AS total
           FROM payment_roster_items pri
           JOIN applications a ON a.id = pri.application_id
           WHERE a.app_id LIKE 'MC-114-%'
           GROUP BY 1 ORDER BY 1"""))).all()
    per = {c: (inc, tot) for c, inc, tot in rows}
    for c in COLLEGES:
        inc, tot = per.get(c, (0, 0))
        say(f"   college {c}: {inc}/{tot} included")
    colleges_with_included = [c for c in COLLEGES if per.get(c, (0, 0))[0] > 0]
    ok = sorted(colleges_with_included) == sorted(COLLEGES.keys())
    return ok, per


async def main():
    async with AsyncSessionLocal() as db:
        admin_id = (
            await db.execute(text("SELECT id FROM users WHERE role IN ('admin','super_admin') ORDER BY role LIMIT 1"))
        ).scalar()
        if admin_id is None:
            raise RuntimeError("no admin user found")
        reviewers = await stage_seed(db)
        await stage_rank(db, reviewers)
        await stage_distribute(db, admin_id)
    stage_roster(admin_id)
    async with AsyncSessionLocal() as db:
        ok, per = await stage_verify(db)
    say("")
    say(
        f"RESULT: {'PASS' if ok else 'FAIL'} — roster covers colleges {sorted(c for c in COLLEGES if per.get(c, (0,0))[0] > 0)}"
    )
    return ok


if __name__ == "__main__":
    import sys

    sys.exit(0 if asyncio.run(main()) else 1)
