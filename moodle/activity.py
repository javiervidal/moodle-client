"""
Activity (course module) helpers.

Supports reading and updating activity settings via Moodle's modedit.php form.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

from .session import MoodleSession


# Date field name suffixes that Moodle uses for timestamp selectors.
# The full field name is e.g. "timeclose[day]", "timeclose[month]", …
_DATE_PARTS = ("day", "month", "year", "hour", "minute")

# Common end-date field names across different activity types.
# Ordered by priority — the first one found in the form wins.
_END_DATE_FIELD_CANDIDATES = [
    "timeclose",    # Quiz, Choice, Feedback, Lesson, …
    "timedue",      # Assignment (older versions)
    "duedate",      # Assignment (newer versions use a flat timestamp, handled separately)
    "cutoffdate",   # Assignment cutoff
    "timeend",      # generic
]


def _parse_form(html: str) -> tuple[dict[str, Any], str]:
    """
    Parse a Moodle modedit form.

    Returns:
        (fields, action)  where `fields` is a flat dict of all input/select
        values and `action` is the form's POST URL.
    """
    soup = BeautifulSoup(html, "lxml")

    # Moodle's edit form has id="mform1"
    form = soup.find("form", {"id": "mform1"})
    if form is None:
        # fallback: any form with modedit in its action
        form = soup.find("form", action=re.compile(r"modedit"))
    if form is None:
        raise RuntimeError(
            "Could not find the activity edit form in the page. "
            "Check that the cmid is correct and you have editing rights."
        )

    action = form.get("action", "")
    fields: dict[str, Any] = {}

    for tag in form.find_all(["input", "select", "textarea"]):
        name = tag.get("name")
        if not name:
            continue

        if tag.name == "select":
            selected = tag.find("option", selected=True)
            fields[name] = selected["value"] if selected else ""
        elif tag.name == "textarea":
            fields[name] = tag.get_text()
        else:
            tag_type = tag.get("type", "text").lower()
            if tag_type in ("checkbox", "radio"):
                if tag.has_attr("checked"):
                    fields[name] = tag.get("value", "1")
                else:
                    fields.setdefault(name, "0")
            else:
                fields[name] = tag.get("value", "")

    return fields, action


def _set_date_fields(fields: dict, base_name: str, dt: datetime) -> None:
    """Overwrite the Moodle date-selector fields for a given base name."""
    fields[f"{base_name}[day]"] = str(dt.day)
    fields[f"{base_name}[month]"] = str(dt.month)
    fields[f"{base_name}[year]"] = str(dt.year)
    fields[f"{base_name}[hour]"] = str(dt.hour)
    fields[f"{base_name}[minute]"] = str(dt.minute)
    # Enable the date (uncheck the "disable" checkbox if present)
    fields[f"{base_name}[enabled]"] = "1"


def _detect_end_date_field(fields: dict) -> str | None:
    """Return the base name of the end-date field found in `fields`."""
    for candidate in _END_DATE_FIELD_CANDIDATES:
        key = f"{candidate}[day]"
        if key in fields:
            return candidate
    return None


def get_activity_info(session: MoodleSession, cmid: int) -> dict:
    """
    Fetch the edit form for a course module and return a summary dict with:
      - cmid
      - name   (activity title)
      - type   (modname, e.g. 'quiz', 'assign')
      - end_date_field  (detected field name, or None)
      - end_date        (current value as datetime, or None)
    """
    resp = session.get(f"/course/modedit.php?update={cmid}&return=0&sr=0")
    fields, _ = _parse_form(resp.text)

    end_field = _detect_end_date_field(fields)
    end_date = None
    if end_field:
        try:
            end_date = datetime(
                year=int(fields.get(f"{end_field}[year]", 0)),
                month=int(fields.get(f"{end_field}[month]", 0)),
                day=int(fields.get(f"{end_field}[day]", 0)),
                hour=int(fields.get(f"{end_field}[hour]", 0)),
                minute=int(fields.get(f"{end_field}[minute]", 0)),
            )
        except (ValueError, TypeError):
            end_date = None

    return {
        "cmid": cmid,
        "name": fields.get("name", fields.get("introeditor[text]", "(unknown)")),
        "type": fields.get("modulename", "(unknown)"),
        "end_date_field": end_field,
        "end_date": end_date,
        "_fields": fields,  # raw, for debugging
    }


def set_activity_end_date(
    session: MoodleSession,
    cmid: int,
    new_end_date: datetime,
    dry_run: bool = False,
) -> dict:
    """
    Change the end date of a course module.

    Returns a result dict with keys:
      - success (bool)
      - cmid
      - end_date_field
      - new_end_date
      - dry_run
    """
    resp = session.get(f"/course/modedit.php?update={cmid}&return=0&sr=0")
    fields, action = _parse_form(resp.text)

    end_field = _detect_end_date_field(fields)
    if end_field is None:
        raise RuntimeError(
            f"No supported end-date field found for cmid={cmid}. "
            f"Fields present: {[k for k in fields if '[' in k]}"
        )

    # Inject our new date values.
    _set_date_fields(fields, end_field, new_end_date)

    # Moodle always requires sesskey in form submissions.
    fields["sesskey"] = session.sesskey

    if dry_run:
        return {
            "success": None,
            "cmid": cmid,
            "end_date_field": end_field,
            "new_end_date": new_end_date,
            "dry_run": True,
            "_fields": fields,
        }

    # Resolve absolute POST URL.
    if not action.startswith("http"):
        action = session.site + "/" + action.lstrip("/")

    post_resp = session.post(action, data=fields)

    # Moodle redirects back to the course on success.
    # A remaining modedit URL in history means it stayed on the form (error).
    success = "modedit.php" not in post_resp.url

    return {
        "success": success,
        "cmid": cmid,
        "end_date_field": end_field,
        "new_end_date": new_end_date,
        "dry_run": False,
        "final_url": post_resp.url,
    }
