"""Allowlist checks for admin-supplied URLs that end up as browser navigation.

Shared by the footer links (rendered as <a href>) and notification action
links (navigated to on click): both are stored-XSS vectors if a `javascript:`
or `data:` value gets through, so both must use the same rules.
"""

from typing import Optional
from urllib.parse import urlparse

HTTP_URL_SCHEMES = frozenset({"http", "https"})

ACTION_URL_ERROR = "行動連結必須是站內路徑（例如 /applications）或 http(s) 網址"


def is_http_url(url: str) -> bool:
    """True for an absolute http(s) URL that names a host."""
    parsed = urlparse(url)
    return parsed.scheme.lower() in HTTP_URL_SCHEMES and bool(parsed.netloc)


def _has_control_chars(url: str) -> bool:
    # Browsers silently drop tab/LF/CR anywhere in a URL, so "/<TAB>/evil.example"
    # parses as the protocol-relative "//evil.example". Other (Unicode) spaces
    # are percent-encoded by the browser and are harmless.
    return any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url)


def validate_action_url(value: Optional[str]) -> Optional[str]:
    """Return a safe notification action_url, None for blank, or raise ValueError.

    Accepts a same-site path ("/applications/1") or an absolute http(s) URL.
    """
    if value is None:
        return None
    url = value.strip()
    if not url:
        return None
    if _has_control_chars(url):
        raise ValueError(ACTION_URL_ERROR)
    if url.startswith("/"):
        if url.startswith("//") or "\\" in url:
            raise ValueError(ACTION_URL_ERROR)
        return url
    if not is_http_url(url):
        raise ValueError(ACTION_URL_ERROR)
    return url
