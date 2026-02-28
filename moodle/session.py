"""
Moodle session management.

Authenticates using a cookie string supplied via --cookie / MOODLE_COOKIE.
Copy the Cookie header from browser DevTools (Network tab) after logging in.
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

    def post_json(self, path: str, payload, **kwargs) -> requests.Response:
        """POST a JSON body (used for Moodle's internal AJAX service)."""
        import json as _json
        url = self.site + path if path.startswith("/") else path
        resp = self._session.post(
            url,
            data=_json.dumps(payload),
            headers={"Content-Type": "application/json"},
            **kwargs,
        )
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        site: str,
        cookie_str: str,
    ) -> "MoodleSession":
        """
        Build an authenticated MoodleSession.

        Args:
            site:       Base URL of the Moodle site, e.g. https://moodle.example.edu
            cookie_str: Raw Cookie header string copied from browser DevTools.
        """
        site = site.rstrip("/")

        s = requests.Session()
        s.headers.update({"User-Agent": "moodle-cli/0.1"})
        s.cookies.update(_parse_cookie_header(cookie_str))

        # Fetch the Moodle home page to grab the sesskey.
        try:
            resp = s.get(site + "/")
            resp.raise_for_status()
        except requests.exceptions.TooManyRedirects:
            raise RuntimeError(
                "Session cookie has expired. Copy a fresh MoodleSession cookie "
                "from browser DevTools and update MOODLE_COOKIE."
            )

        sesskey = _extract_sesskey(resp.text)
        if not sesskey:
            raise RuntimeError(
                "Could not extract sesskey from Moodle. "
                "Are you sure you are logged in?"
            )

        return cls(site=site, session=s, sesskey=sesskey)
