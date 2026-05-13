"""
Tests for `EmailTemplateLoader` (filesystem-backed; uses tmp_path).

This loader is the legacy fallback for emails scheduled before the
React Email migration (2025-10-13). Bugs here mean queued legacy
notifications go out with unreplaced `{{variable}}` placeholders to
students — visible, embarrassing, and audit-trail noise.

Methods covered (11 cases):
- `load_template`           : read + cache + FileNotFoundError
- `render`                  : {{var}} substitution; unreplaced warning
- `clear_cache`             : forces re-read
- `list_available_templates`: glob *.html, sorted, no extension
"""

import logging

import pytest

from app.services.email_template_loader import EmailTemplateLoader


@pytest.fixture
def loader(tmp_path):
    """Loader rooted at an isolated tmp directory — no global filesystem state."""
    return EmailTemplateLoader(template_dir=str(tmp_path))


def _write(tmp_path, name: str, body: str) -> None:
    (tmp_path / f"{name}.html").write_text(body, encoding="utf-8")


# ─── load_template ────────────────────────────────────────────────────


def test_load_template_reads_file_contents(loader, tmp_path):
    _write(tmp_path, "welcome", "<p>Hi {{name}}</p>")
    assert loader.load_template("welcome") == "<p>Hi {{name}}</p>"


def test_load_template_caches_after_first_read(loader, tmp_path):
    """Second read hits the in-memory cache — modifying the file after the
    first read must NOT change the returned content."""
    _write(tmp_path, "cached", "v1")
    assert loader.load_template("cached") == "v1"

    # Overwrite the file; cached value should still be returned.
    _write(tmp_path, "cached", "v2-on-disk")
    assert loader.load_template("cached") == "v1"


def test_load_template_missing_file_raises_with_helpful_message(loader):
    with pytest.raises(FileNotFoundError, match="Email template not found"):
        loader.load_template("does-not-exist")


# ─── render ───────────────────────────────────────────────────────────


def test_render_replaces_single_variable(loader, tmp_path):
    _write(tmp_path, "t", "<p>Hello {{name}}</p>")
    assert loader.render("t", {"name": "Alice"}) == "<p>Hello Alice</p>"


def test_render_replaces_multiple_variables(loader, tmp_path):
    _write(tmp_path, "t", "<p>{{greeting}}, {{name}}!</p>")
    out = loader.render("t", {"greeting": "Hi", "name": "Bob"})
    assert out == "<p>Hi, Bob!</p>"


def test_render_stringifies_non_string_values(loader, tmp_path):
    """Context values can be int/float — render coerces via str()."""
    _write(tmp_path, "t", "<p>#{{n}} on {{ratio}}</p>")
    assert loader.render("t", {"n": 42, "ratio": 3.14}) == "<p>#42 on 3.14</p>"


def test_render_warns_on_unreplaced_variables(loader, tmp_path, caplog):
    """If a template references a variable not in context, log a warning
    naming it — this is the production-visible signal for missing data."""
    _write(tmp_path, "t", "<p>{{a}} / {{b}} / {{c}}</p>")
    with caplog.at_level(logging.WARNING, logger="app.services.email_template_loader"):
        out = loader.render("t", {"a": "1"})
    assert "1 / {{b}} / {{c}}" in out
    assert any("unreplaced variables" in rec.message for rec in caplog.records)


def test_render_uses_cache_so_filesystem_changes_are_invisible(loader, tmp_path):
    """`render` calls `load_template`, which caches. Once loaded, swapping
    the file on disk should not affect rendering until clear_cache is called."""
    _write(tmp_path, "t", "v1 {{x}}")
    assert loader.render("t", {"x": "ok"}) == "v1 ok"

    _write(tmp_path, "t", "v2 {{x}}")
    assert loader.render("t", {"x": "ok"}) == "v1 ok"  # still cached


# ─── clear_cache ──────────────────────────────────────────────────────


def test_clear_cache_forces_re_read_from_disk(loader, tmp_path):
    _write(tmp_path, "t", "v1")
    assert loader.load_template("t") == "v1"

    _write(tmp_path, "t", "v2")
    loader.clear_cache()
    assert loader.load_template("t") == "v2"


# ─── list_available_templates ─────────────────────────────────────────


def test_list_available_templates_returns_sorted_names_without_extension(loader, tmp_path):
    _write(tmp_path, "welcome", "x")
    _write(tmp_path, "alert", "x")
    _write(tmp_path, "reminder", "x")
    # Non-html files should be ignored.
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")

    assert loader.list_available_templates() == ["alert", "reminder", "welcome"]


def test_list_available_templates_missing_dir_returns_empty():
    """If the template directory doesn't exist (deployment mismatch),
    return [] instead of raising — caller can degrade gracefully."""
    loader = EmailTemplateLoader(template_dir="/tmp/__definitely_does_not_exist_12345__")
    assert loader.list_available_templates() == []
