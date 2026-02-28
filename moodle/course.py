"""
Course listing helpers.

Uses Moodle's internal AJAX service (the same endpoint the dashboard calls)
to retrieve enrolled courses without needing an API token.
Falls back to scraping /course/index.php if the AJAX call fails.
"""
from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from .session import MoodleSession


def _ajax_list_courses(session: MoodleSession, starred: bool = False) -> list[dict[str, Any]]:
    """
    Call core_course_get_enrolled_courses_by_timeline_classification via
    Moodle's internal service endpoint.

    Returns a list of course dicts with at minimum:
      id, fullname, shortname, category (name string)
    """
    classification = "favourites" if starred else "all"
    payload = [
        {
            "index": 0,
            "methodname": "core_course_get_enrolled_courses_by_timeline_classification",
            "args": {
                "offset": 0,
                "limit": 0,
                "classification": classification,
                "sort": "fullname",
                "customfieldname": "",
                "customfieldvalue": "",
            },
        }
    ]

    resp = session.post_json(
        f"/lib/ajax/service.php?sesskey={session.sesskey}"
        "&info=core_course_get_enrolled_courses_by_timeline_classification",
        payload,
    )

    data = resp.json()

    # Response is a list of method results; index 0 is ours.
    result = data[0]
    if result.get("error"):
        raise RuntimeError(f"AJAX error: {result.get('exception', result)}")

    courses = result["data"].get("courses", [])
    return [
        {
            "id": c["id"],
            "fullname": c.get("fullname", ""),
            "shortname": c.get("shortname", ""),
            "category": c.get("coursecategory", ""),
            "visible": c.get("visible", True),
        }
        for c in courses
    ]


def _scrape_list_courses(session: MoodleSession) -> list[dict[str, Any]]:
    """
    Fallback: scrape /course/index.php for course links.
    Works on any Moodle version but gives less metadata.
    Follows pagination automatically.
    """
    courses: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    page = 0
    course_link_re = re.compile(r"/course/view\.php\?id=(\d+)")

    while True:
        resp = session.get(f"/course/index.php?page={page}")
        soup = BeautifulSoup(resp.text, "lxml")

        found_any = False
        for a in soup.find_all("a", href=course_link_re):
            href = a["href"]
            m = course_link_re.search(href)
            if not m:
                continue
            course_id = int(m.group(1))
            if course_id in seen_ids:
                continue
            seen_ids.add(course_id)
            found_any = True
            courses.append(
                {
                    "id": course_id,
                    "fullname": a.get_text(strip=True),
                    "shortname": "",
                    "category": "",
                    "visible": True,
                }
            )

        # Stop when no new courses are found (end of pagination or single page).
        if not found_any:
            break
        page += 1

    return courses


def list_courses(session: MoodleSession, starred: bool = False) -> list[dict[str, Any]]:
    """
    Return all courses the current user is enrolled in (or can access).

    Tries the AJAX endpoint first; falls back to HTML scraping.
    Each dict has: id, fullname, shortname, category, visible.
    If starred=True, only returns courses marked as favourites.
    The scrape fallback does not support starred filtering.
    """
    try:
        return _ajax_list_courses(session, starred=starred)
    except Exception:
        return _scrape_list_courses(session)
