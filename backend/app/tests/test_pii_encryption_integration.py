"""Integration test: StudentDataJSON transparently encrypts/decrypts std_pid.

Verifies the storage boundary:
- The raw DB column holds the AES-256-GCM envelope (``pii:v1:...``).
- Reading the row back through the ORM returns plaintext.
- Other keys inside ``student_data`` pass through unchanged.
- Idempotent persists (no double-encryption).
"""

from __future__ import annotations

import base64
import hashlib
import json

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import pii_crypto

_PLAINTEXT_PID = "A123456789"


def _b64key(seed: str) -> str:
    raw = hashlib.sha256(seed.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@pytest.fixture
def keys_env(monkeypatch):
    monkeypatch.setenv("PII_ENCRYPTION_KEYS", json.dumps({"v1": _b64key("integ-v1")}))
    monkeypatch.setenv("PII_ENCRYPTION_ACTIVE_VERSION", "v1")
    monkeypatch.setenv("ENVIRONMENT", "production")
    pii_crypto.reset_key_cache()
    yield
    pii_crypto.reset_key_cache()


@pytest.fixture
def engine_and_session(keys_env):
    # Isolated SQLite engine for this test so the Application table can be
    # built with exactly the columns we need without dragging in every other
    # model relationship.
    from sqlalchemy import Column, Integer
    from sqlalchemy.orm import declarative_base

    from app.core.encrypted_json import StudentDataJSON

    Base = declarative_base()

    class App(Base):
        __tablename__ = "applications_pii_test"
        id = Column(Integer, primary_key=True, autoincrement=True)
        student_data = Column(StudentDataJSON)

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, Session, App


def test_db_column_holds_envelope_orm_returns_plaintext(engine_and_session):
    engine, Session, App = engine_and_session
    with Session() as s:
        row = App(student_data={"std_pid": _PLAINTEXT_PID, "std_cname": "Ada"})
        s.add(row)
        s.commit()
        row_id = row.id

    # Raw column inspection — bypasses the TypeDecorator.
    with engine.connect() as conn:
        raw = conn.execute(
            text("SELECT student_data FROM applications_pii_test WHERE id = :id"),
            {"id": row_id},
        ).scalar()
    raw_dict = json.loads(raw) if isinstance(raw, str) else raw
    assert raw_dict["std_pid"].startswith("pii:v1:")
    assert raw_dict["std_pid"] != _PLAINTEXT_PID
    # Non-PII keys unmodified at rest.
    assert raw_dict["std_cname"] == "Ada"

    # ORM read decrypts back to plaintext.
    with Session() as s:
        fetched = s.get(App, row_id)
        assert fetched.student_data["std_pid"] == _PLAINTEXT_PID
        assert fetched.student_data["std_cname"] == "Ada"


def test_idempotent_persist(engine_and_session):
    """Persisting a row whose dict already has an enveloped std_pid must not double-wrap."""
    engine, Session, App = engine_and_session

    pre_envelope = pii_crypto.encrypt_pii(_PLAINTEXT_PID)
    with Session() as s:
        row = App(student_data={"std_pid": pre_envelope, "x": 1})
        s.add(row)
        s.commit()
        row_id = row.id

    with engine.connect() as conn:
        raw = conn.execute(
            text("SELECT student_data FROM applications_pii_test WHERE id = :id"),
            {"id": row_id},
        ).scalar()
    raw_dict = json.loads(raw) if isinstance(raw, str) else raw
    # Still the same envelope, not re-encrypted (would change the nonce).
    assert raw_dict["std_pid"] == pre_envelope

    with Session() as s:
        fetched = s.get(App, row_id)
        assert fetched.student_data["std_pid"] == _PLAINTEXT_PID


def test_none_and_empty_pid_passthrough(engine_and_session):
    engine, Session, App = engine_and_session
    with Session() as s:
        s.add(App(student_data={"std_pid": None, "k": "v"}))
        s.add(App(student_data={"std_pid": "", "k": "v"}))
        s.add(App(student_data={"std_cname": "no-pid-key"}))
        s.commit()

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT student_data FROM applications_pii_test")).fetchall()
    for (raw,) in rows:
        rd = json.loads(raw) if isinstance(raw, str) else raw
        pid = rd.get("std_pid")
        assert pid in (None, "") or "std_pid" not in rd
