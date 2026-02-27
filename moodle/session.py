"""
Moodle session management.

Reuses an existing browser session by extracting cookies from Chrome or Firefox.
Falls back to a manually supplied cookie string.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
from requests import Session


# Moodle embeds the sesskey in every page as a JS variable or data attribute.
# We look for the most common patterns across Moodle versions.
_SESSKEY_PATTERNS = [
    re.compile(r'"sesskey"\s*:\s*"([a-zA-Z0-9]+)"'),
    re.compile(r"'sesskey'\s*:\s*'([a-zA-Z0-9]+)'"),
    re.compile(r'sesskey=([a-zA-Z0-9]+)'),
    re.compile(r'name="sesskey"\s+value="([a-zA-Z0-9]+)"'),
    re.compile(r'value="([a-zA-Z0-9]+)"\s+name="sesskey"'),
]


def _extract_sesskey(html: str) -> str | None:
    for pattern in _SESSKEY_PATTERNS:
        m = pattern.search(html)
        if m:
            return m.group(1)
    return None


def _domain_from_url(url: str) -> str:
    return urlparse(url).netloc


def _load_browser_cookies(domain: str) -> dict:
    """Try Chrome then Firefox; return a plain dict of name→value."""
    try:
        import browser_cookie3  # type: ignore
    except ImportError:
        raise RuntimeError(
            "browser_cookie3 is not installed. Run: pip install browser-cookie3"
        )

    for loader_name in ("chrome", "firefox", "chromium", "edge"):
        loader = getattr(browser_cookie3, loader_name, None)
        if loader is None:
            continue
        try:
            jar = loader(domain_name=domain)
            cookies = {c.name: c.value for c in jar}
            if cookies:
                return cookies
        except Exception:
            continue

    return {}


def _parse_cookie_header(cookie_str: str) -> dict:
    """Parse a raw Cookie header string (name=value; name=value …)."""
    result = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            name, _, value = part.partition("=")
            result[name.strip()] = value.strip()
    return result


class MoodleSession:
    """Authenticated HTTP session for a single Moodle site."""

    def __init__(self, site: str, session: Session, sesskey: str):
        self.site = site.rstrip("/")
        self._session = session
        self.sesskey = sesskey

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------

    def get(self, path: str, **kwargs) -> requests.Response:
        url = self.site + path if path.startswith("/") else path
        resp = self._session.get(url, **kwargs)
        resp.raise_for_status()
        return resp

    def post(self, path: str, data: dict, **kwargs) -> requests.Response:
        url = self.site + path if path.startswith("/") else path
        resp = self._session.post(url, data=data, **kwargs)
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        site: str,
        cookie_str: str | None = None,
    ) -> "MoodleSession":
        """
        Build an authenticated MoodleSession.

        Args:
            site:       Base URL of the Moodle site, e.g. https://moodle.example.edu
            cookie_str: Raw Cookie header string (optional).
                        If omitted, cookies are read from the running browser.
        """
        site = site.rstrip("/")
        domain = _domain_from_url(site)

        s = requests.Session()
        s.headers.update({"User-Agent": "moodle-cli/0.1"})

        if cookie_str:
            cookies = _parse_cookie_header(cookie_str)
        else:
            cookies = _load_browser_cookies(domain)
            if not cookies:
                raise RuntimeError(
                    f"No cookies found for {domain} in Chrome/Firefox.\n"
                    "Make sure you are logged in, or pass --cookie with the "
                    "Cookie header from browser DevTools."
                )

        s.cookies.update(cookies)

        # Fetch the Moodle home page to grab the sesskey.
        resp = s.get(site + "/")
        resp.raise_for_status()

        sesskey = _extract_sesskey(resp.text)
        if not sesskey:
            raise RuntimeError(
                "Could not extract sesskey from Moodle. "
                "Are you sure you are logged in?"
            )

        return cls(site=site, session=s, sesskey=sesskey)
