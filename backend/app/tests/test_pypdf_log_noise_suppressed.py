"""pypdf's auto-repair WARNINGs must not reach the prod log stream (issue #1515)."""

import logging

import app.main  # noqa: F401  (configures third-party logger levels on import)


def test_pypdf_child_loggers_suppress_warnings():
    for name in ("pypdf", "pypdf.generic._link", "pypdf._reader"):
        logger = logging.getLogger(name)
        assert not logger.isEnabledFor(logging.WARNING), name
        assert logger.isEnabledFor(logging.ERROR), name


def test_pdf_merge_warnings_still_emitted():
    assert logging.getLogger("app.services.pdf_merge").isEnabledFor(logging.WARNING)
