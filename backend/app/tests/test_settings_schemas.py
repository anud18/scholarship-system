"""
Tests for `app/schemas/settings.py`.

The schemas in this module gate:
  - **System settings** (key/value with public-flag) edited via the
    admin UI.
  - **Email templates** (subject + body templates) configured by admins.
  - **EmailConfig** — SMTP connection parameters. Regressions here
    surface as silent email-send failures.
  - **EmailSendRequest** — every direct send-email call must pass
    EmailStr validation; bypassing it lets typos like
    "professor@nyc.edu.t" through to the SMTP layer (bounces).

19 cases pinning the 7 schemas in the module.
"""

import pytest
from pydantic import ValidationError

from app.schemas.settings import (
    EmailConfig,
    EmailSendRequest,
    EmailTemplateBase,
    EmailTemplateCreate,
    EmailTemplateUpdate,
    SystemSettingBase,
    SystemSettingUpdate,
)

# ─── SystemSettingBase / Create ─────────────────────────────────────


def test_system_setting_required_fields():
    # Pin: key + value + category required. is_public defaults to
    # False, description optional.
    with pytest.raises(ValidationError):
        SystemSettingBase(  # type: ignore[call-arg]
            key="x",
            value="y",
            # category missing
        )


def test_system_setting_is_public_defaults_to_false():
    # Pin: is_public is False by default. A regression flipping the
    # default to True would silently expose private settings to
    # unauthenticated users.
    s = SystemSettingBase(key="x", value="y", category="general")
    assert s.is_public is False


def test_system_setting_create_inherits_base_fields():
    # Pin: Create is a thin alias of Base (no extra fields). Don't
    # widen silently.
    fields = set(SystemSettingBase.model_fields.keys())
    assert fields == {"key", "value", "description", "is_public", "category"}


# ─── SystemSettingUpdate ────────────────────────────────────────────


def test_system_setting_update_all_optional():
    # Pin: PATCH semantics — every field optional, empty body is a
    # valid (no-op) update. A regression making any required would
    # break partial-update API.
    obj = SystemSettingUpdate()
    assert obj.value is None
    assert obj.description is None
    assert obj.is_public is None
    assert obj.category is None


def test_system_setting_update_excludes_key():
    # Pin: key is NOT in Update — keys are immutable identifiers, the
    # endpoint must require a fresh setting for a key change. A
    # regression adding key here would let admins silently rename
    # settings under-the-hood, breaking external references.
    assert "key" not in SystemSettingUpdate.model_fields


# ─── EmailTemplateBase / Create / Update ────────────────────────────


def test_email_template_required_fields():
    # Pin: key, subject_template, body_template, category all required.
    with pytest.raises(ValidationError):
        EmailTemplateBase(  # type: ignore[call-arg]
            key="x",
            subject_template="Hello",
            # body_template missing
            category="application",
        )


def test_email_template_cc_validates_email_addresses():
    # Pin: cc is List[EmailStr] — typo-cc'ing on a template would let
    # every fire-off bounce. EmailStr rejects malformed addresses.
    with pytest.raises(ValidationError):
        EmailTemplateBase(
            key="x",
            subject_template="Hello",
            body_template="Body",
            category="application",
            cc=["not-an-email"],
        )


def test_email_template_cc_accepts_well_formed_emails():
    t = EmailTemplateBase(
        key="x",
        subject_template="Hello",
        body_template="Body",
        category="application",
        cc=["dept@nycu.edu.tw", "scholarship@nycu.edu.tw"],
    )
    assert len(t.cc) == 2


def test_email_template_variables_optional_list_of_strings():
    # Pin: variables is Optional[List[str]] — when present, must be a
    # list. A regression accepting a single string would break the
    # template engine's iteration.
    t = EmailTemplateBase(
        key="x",
        subject_template="Hello {name}",
        body_template="Body {amount}",
        category="application",
        variables=["name", "amount"],
    )
    assert t.variables == ["name", "amount"]


def test_email_template_update_all_optional():
    # Pin: PATCH semantics. Like SystemSettingUpdate, key omitted.
    obj = EmailTemplateUpdate()
    assert obj.subject_template is None
    assert "key" not in EmailTemplateUpdate.model_fields


# ─── EmailConfig ────────────────────────────────────────────────────


def test_email_config_all_smtp_fields_required():
    # Pin: SMTP credentials non-optional — a regression making any
    # optional would let admins partially configure SMTP and have
    # send_email silently NOOP.
    with pytest.raises(ValidationError):
        EmailConfig(  # type: ignore[call-arg]
            smtp_host="smtp.nycu.edu.tw",
            smtp_port=587,
            # smtp_user missing
            smtp_password="secret",
            default_from_email="noreply@nycu.edu.tw",
            default_from_name="Scholarship System",
        )


def test_email_config_use_tls_defaults_true():
    # Pin: TLS on by default. SECURITY-CRITICAL — a regression
    # flipping this to False would silently send credentials in
    # plaintext.
    c = EmailConfig(
        smtp_host="smtp.nycu.edu.tw",
        smtp_port=587,
        smtp_user="user",
        smtp_password="pw",
        default_from_email="noreply@nycu.edu.tw",
        default_from_name="Scholarship System",
    )
    assert c.use_tls is True


def test_email_config_default_from_email_must_be_valid():
    # Pin: from-email EmailStr enforced. Otherwise typos in admin UI
    # would let send_email reject the entire message at the SMTP layer.
    with pytest.raises(ValidationError):
        EmailConfig(
            smtp_host="smtp.nycu.edu.tw",
            smtp_port=587,
            smtp_user="user",
            smtp_password="pw",
            default_from_email="not an email",
            default_from_name="Scholarship System",
        )


def test_email_config_reply_to_optional():
    c = EmailConfig(
        smtp_host="smtp.nycu.edu.tw",
        smtp_port=587,
        smtp_user="user",
        smtp_password="pw",
        default_from_email="noreply@nycu.edu.tw",
        default_from_name="Scholarship System",
    )
    assert c.reply_to_email is None
    assert c.reply_to_name is None


def test_email_config_smtp_port_must_be_int():
    # Pin: port is int. Accepting string would break the smtplib
    # connect call at runtime.
    with pytest.raises(ValidationError):
        EmailConfig(
            smtp_host="smtp.nycu.edu.tw",
            smtp_port="not an int",  # type: ignore[arg-type]
            smtp_user="user",
            smtp_password="pw",
            default_from_email="noreply@nycu.edu.tw",
            default_from_name="Scholarship System",
        )


# ─── EmailSendRequest ────────────────────────────────────────────────


def test_email_send_request_requires_template_key_and_to_emails():
    with pytest.raises(ValidationError):
        EmailSendRequest(template_key="welcome")  # type: ignore[call-arg]


def test_email_send_request_to_emails_validated():
    # Pin: every recipient must be a valid EmailStr — a regression
    # accepting string would let admins fire mass mailers to bad
    # addresses without warning.
    with pytest.raises(ValidationError):
        EmailSendRequest(
            template_key="welcome",
            to_emails=["valid@x.com", "not-an-email"],
        )


def test_email_send_request_variables_optional_dict():
    # Pin: variables is Optional[Dict[str, Any]] — arbitrary keys/
    # values for template substitution.
    r = EmailSendRequest(
        template_key="welcome",
        to_emails=["a@b.com"],
        variables={"name": "王小明", "amount": 50000},
    )
    assert r.variables == {"name": "王小明", "amount": 50000}


def test_email_send_request_attachments_optional_list_of_dicts():
    # Pin: attachments is Optional[List[Dict[str, Any]]] — the email
    # service expects this shape. A regression to flat dict would
    # crash the attachment loop.
    r = EmailSendRequest(
        template_key="welcome",
        to_emails=["a@b.com"],
        attachments=[{"filename": "doc.pdf", "content_type": "application/pdf"}],
    )
    assert len(r.attachments) == 1
