"""Tests for the shared read-only SQL guard (issue #1223 finding A).

`email_automation_rules.condition_query` is free-form SQL stored in the DB and
executed verbatim. The guard is what makes that safe, so it is pinned from both
sides: every query the system actually ships must pass, and every escape route
must be refused.
"""

import pytest

from app.core.sql_read_only_guard import (
    MAX_QUERY_LENGTH,
    UnsafeConditionQueryError,
    assert_read_only_select,
    mask_literals,
)

# The two condition_query strings that actually ship (db/seed_scholarship_configs.py).
SEEDED_STUDENT_QUERY = """
    SELECT email FROM (
        SELECT applications.student_data->>'com_email' as email
        FROM applications
        WHERE applications.id = {application_id}
        AND applications.student_data->>'com_email' IS NOT NULL
        AND applications.student_data->>'com_email' != ''

        UNION

        SELECT users.email
        FROM applications
        JOIN users ON applications.user_id = users.id
        WHERE applications.id = {application_id}
        AND users.email IS NOT NULL
        AND users.email != ''
    ) emails
    WHERE email IS NOT NULL
"""

SEEDED_PROFESSOR_QUERY = """
    SELECT COALESCE(u.email, up.advisor_email) AS email
    FROM applications a
    LEFT JOIN users u ON u.id = a.professor_id
    LEFT JOIN user_profiles up ON up.user_id = a.user_id
    WHERE a.id = {application_id}
    AND COALESCE(u.email, up.advisor_email) IS NOT NULL
    AND COALESCE(u.email, up.advisor_email) != ''
"""


# ---------------------------------------------------------------------------
# Everything the system actually ships must keep working
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query", [SEEDED_STUDENT_QUERY, SEEDED_PROFESSOR_QUERY])
def test_shipped_seeded_queries_are_accepted(query):
    assert_read_only_select(query)


def test_union_is_allowed():
    """UNION is a read-only set operator and the shipped student rule uses it.

    The old blacklist rejected it, which made that seeded rule impossible to
    re-save from the admin edit dialog.
    """
    assert_read_only_select("SELECT a FROM t UNION SELECT b FROM u")


@pytest.mark.parametrize(
    "query",
    [
        "SELECT created_at FROM applications",  # CREATE ⊂ created_at
        "SELECT updated_at FROM applications",  # UPDATE ⊂ updated_at
        "SELECT email FROM users LIMIT 10 OFFSET 5",  # SET ⊂ OFFSET
        "SELECT id FROM t WHERE name = 'insert into'",  # keyword inside a literal
        "SELECT a FROM t -- drop table users",  # keyword in a line comment
        "SELECT a FROM t /* delete from users */",  # keyword in a block comment
        "SELECT a FROM t WHERE x = ';'",  # semicolon inside a literal
    ],
)
def test_legitimate_queries_are_not_false_positived(query):
    """These are the false positives that made the old validator reject real SQL."""
    assert_read_only_select(query)


def test_with_cte_is_accepted():
    assert_read_only_select("WITH x AS (SELECT 1 AS a) SELECT a FROM x")


def test_trailing_semicolon_is_accepted():
    assert_read_only_select("SELECT email FROM users;")


# ---------------------------------------------------------------------------
# Escape routes must be refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM users",
        "UPDATE users SET email = 'x'",
        "INSERT INTO users (email) VALUES ('x')",
        "DROP TABLE users",
        "TRUNCATE users",
        "ALTER TABLE users ADD COLUMN x int",
        "GRANT ALL ON users TO public",
    ],
)
def test_non_select_statements_refused(query):
    with pytest.raises(UnsafeConditionQueryError):
        assert_read_only_select(query)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT 1; DROP TABLE users",
        # The old check only fired when the query did NOT end in a semicolon, so
        # this exact shape slipped through.
        "SELECT 1; LOCK TABLE users;",
        "SELECT 1;SELECT 2",
    ],
)
def test_multiple_statements_refused(query):
    with pytest.raises(UnsafeConditionQueryError, match="multiple SQL statements"):
        assert_read_only_select(query)


@pytest.mark.parametrize(
    "query",
    [
        # SET LOCAL transaction_read_only does NOT stop these, and the app's DB
        # role is a superuser — so without the identifier deny-list "read-only"
        # would still mean arbitrary server file read, exfiltrated via the
        # resolved recipient list.
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT pg_read_binary_file('/etc/passwd')",
        "SELECT pg_ls_dir('/')",
        "SELECT pg_stat_file('/etc/passwd')",
        "SELECT lo_import('/etc/passwd')",
        "SELECT dblink('dbname=x', 'SELECT 1')",
        "SELECT dblink_exec('dbname=x', 'DROP TABLE users')",
        # Executes its argument as SQL, bypassing every static check.
        "SELECT query_to_xml('DELETE FROM users', true, true, '')",
        "SELECT pg_sleep(60)",
        "SELECT pg_terminate_backend(1)",
    ],
)
def test_filesystem_and_string_executing_functions_refused(query):
    with pytest.raises(UnsafeConditionQueryError, match="forbidden keyword"):
        assert_read_only_select(query)


def test_dollar_quoting_refused():
    """Dollar-quoting can hide arbitrary text from every scanner above."""
    with pytest.raises(UnsafeConditionQueryError, match="dollar-quoted"):
        assert_read_only_select("SELECT $$ ; DROP TABLE users $$")


def test_over_length_query_refused():
    with pytest.raises(UnsafeConditionQueryError, match="maximum length"):
        assert_read_only_select("SELECT " + "a" * MAX_QUERY_LENGTH)


@pytest.mark.parametrize(
    "query,message",
    [
        ("SELECT 'unterminated", "unterminated quoted string"),
        ("SELECT a /* unterminated", "unterminated block comment"),
    ],
)
def test_unterminated_constructs_refused(query, message):
    with pytest.raises(UnsafeConditionQueryError, match=message):
        assert_read_only_select(query)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT \"pg_read_file\"('/etc/passwd')",
        "SELECT \"PG_READ_FILE\"('/etc/passwd')",
        "SELECT pg_catalog.\"pg_read_file\"('/etc/passwd')",
        "SELECT \"lo_import\"('/etc/passwd')",
        "SELECT \"dblink_exec\"('dbname=x', 'DROP TABLE users')",
        "SELECT \"query_to_xml\"('DELETE FROM users', true, true, '')",
        "SELECT \"pg_ls_dir\"('/')",
    ],
)
def test_quoting_a_forbidden_name_does_not_bypass_the_deny_list(query):
    """PostgreSQL resolves "pg_read_file" to the SAME function as pg_read_file.

    An earlier revision masked double-quoted identifiers along with string
    literals before scanning, so every entry in FORBIDDEN_IDENTIFIERS could be
    bypassed by quoting it — and the rejection message helpfully suggested doing
    exactly that. The name scan now preserves quoted-identifier content.
    """
    with pytest.raises(UnsafeConditionQueryError, match="forbidden keyword"):
        assert_read_only_select(query)


def test_rejection_message_does_not_suggest_quoting():
    """Quoting does not make the name safe; it only used to hide it from the scan."""
    with pytest.raises(UnsafeConditionQueryError) as exc_info:
        assert_read_only_select("SELECT pg_read_file('/etc/passwd')")
    assert "quote it" not in str(exc_info.value)


def test_a_quoted_forbidden_keyword_identifier_is_rejected_fail_closed():
    """`SELECT "delete" FROM t` is legal SQL but is refused.

    That is the deliberate cost of scanning quoted-identifier content: the
    alternative is a total bypass of the function deny-list. No shipped query
    uses a quoted forbidden keyword as an identifier.
    """
    with pytest.raises(UnsafeConditionQueryError, match="forbidden keyword"):
        assert_read_only_select('SELECT "delete" FROM t')


def test_a_quoted_non_forbidden_identifier_still_works():
    """Only names on the deny-list are affected — ordinary quoted identifiers,
    including mixed-case column names, keep working."""
    assert_read_only_select('SELECT "Email", "std_academyno" FROM users')


def test_a_semicolon_inside_a_quoted_identifier_is_not_a_statement_separator():
    """The STRUCTURAL view still masks quoted identifiers, so the two views do
    not interfere with each other."""
    assert_read_only_select('SELECT "weird;name" FROM t')


# ---------------------------------------------------------------------------
# mask_literals — the length invariant the placeholder rewriter depends on
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 'abc' FROM t",
        'SELECT "col" FROM t',
        "SELECT a FROM t -- comment\nWHERE x = 1",
        "SELECT a /* c */ FROM t",
        "SELECT a /* nested /* inner */ still */ FROM t",
        "SELECT 'it''s' FROM t",
        SEEDED_STUDENT_QUERY,
    ],
)
def test_mask_preserves_length(sql):
    """Offsets in the mask must map 1:1 onto the original — bind_placeholders
    rewrites the ORIGINAL by offsets found in the MASK."""
    assert len(mask_literals(sql)) == len(sql)


def test_mask_blanks_literal_content_but_keeps_sql_structure():
    masked = mask_literals("SELECT 'secret' FROM t WHERE id = 1")
    assert "secret" not in masked
    assert "SELECT" in masked and "FROM t WHERE id = 1" in masked


def test_mask_blanks_a_semicolon_hidden_in_a_literal():
    masked = mask_literals("SELECT ';' FROM t")
    assert ";" not in masked
