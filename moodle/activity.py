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


def list_activities(session: MoodleSession, course_id: int) -> list[dict[str, Any]]:
    """
    Scrape /course/view.php?id=<course_id> and return all course modules,
    including labels/HTML blocks which have no link of their own.

    Each dict has: cmid, name, type, section, visible.
    """
    resp = session.get(f"/course/view.php?id={course_id}")
    soup = BeautifulSoup(resp.text, "lxml")

    activities: list[dict[str, Any]] = []
    mod_link_re = re.compile(r"/mod/[^/]+/view\.php\?id=\d+")

    for section_el in soup.find_all("li", id=re.compile(r"^section-")):
        heading = section_el.find(["h3", "h4"], class_=re.compile(r"sectionname|section-title"))
        section_title = heading.get_text(strip=True) if heading else section_el.get("aria-label", "")

        for mod_el in section_el.find_all("li", id=re.compile(r"^module-")):
            # cmid from the li id="module-<cmid>"
            m = re.match(r"module-(\d+)", mod_el.get("id", ""))
            if not m:
                continue
            cmid = int(m.group(1))

            # type from class="activity <modname> modtype_<modname> ..."
            classes = mod_el.get("class", [])
            mod_type = next(
                (cls[len("modtype_"):] for cls in classes if cls.startswith("modtype_")),
                "unknown",
            )

            # Visibility: Moodle 4.x adds "hiddenactivity" to the inner
            # div.activity-item when the module is hidden from students.
            activity_item = mod_el.find("div", class_="activity-item")
            if activity_item:
                item_classes = activity_item.get("class", [])
                visible = "hiddenactivity" not in item_classes
            else:
                visible = "dimmed" not in classes

            # name: labels display HTML inline with no link; others have a link
            if mod_type == "label":
                content = mod_el.find("div", class_=re.compile(r"no-overflow|contentafterlink"))
                if content:
                    text = content.get_text(strip=True)
                    name = (text[:60] + "…") if len(text) > 60 else text or "(empty label)"
                else:
                    name = "(label)"
            else:
                a = mod_el.find("a", href=mod_link_re)
                if a:
                    name_span = a.find("span", class_="instancename")
                    if name_span:
                        for hidden in name_span.find_all("span", class_="accesshide"):
                            hidden.decompose()
                        name = name_span.get_text(strip=True)
                    else:
                        name = a.get_text(strip=True)
                else:
                    name = mod_el.get_text(strip=True)[:60]

            activities.append({
                "cmid": cmid,
                "name": name,
                "type": mod_type,
                "section": section_title,
                "visible": visible,
            })

    return activities


def get_module_raw_html(session: MoodleSession, course_id: int, cmid: int) -> str:
    """Return the raw HTML of the li#module-<cmid> element for debugging."""
    resp = session.get(f"/course/view.php?id={course_id}")
    soup = BeautifulSoup(resp.text, "lxml")
    el = soup.find("li", id=f"module-{cmid}")
    if el is None:
        raise RuntimeError(f"module-{cmid} not found in course {course_id}")
    return el.prettify()


def set_activity_visibility(session: MoodleSession, cmid: int, visible: bool) -> None:
    """Show or hide a course module via /course/mod.php."""
    action = "show" if visible else "hide"
    session.get(f"/course/mod.php?sesskey={session.sesskey}&sr=0&{action}={cmid}")


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


def get_activity_html(session: MoodleSession, cmid: int) -> str:
    """
    Return the raw HTML content of a label/text activity (introeditor[text]).
    """
    resp = session.get(f"/course/modedit.php?update={cmid}&return=0&sr=0")
    fields, _ = _parse_form(resp.text)
    html = fields.get("introeditor[text]")
    if html is None:
        raise RuntimeError(
            f"No HTML content field found for cmid={cmid}. "
            "Is this a label or text activity?"
        )
    return html


def set_activity_html(
    session: MoodleSession,
    cmid: int,
    new_html: str,
    dry_run: bool = False,
) -> dict:
    """
    Replace the HTML content (introeditor[text]) of a label/text activity.
    """
    resp = session.get(f"/course/modedit.php?update={cmid}&return=0&sr=0")
    fields, action = _parse_form(resp.text)

    if "introeditor[text]" not in fields:
        raise RuntimeError(
            f"No HTML content field found for cmid={cmid}. "
            "Is this a label or text activity?"
        )

    fields["introeditor[text]"] = new_html
    fields["sesskey"] = session.sesskey

    if dry_run:
        return {"success": None, "cmid": cmid, "dry_run": True, "_fields": fields}

    if not action.startswith("http"):
        action = session.site + "/" + action.lstrip("/")

    post_resp = session.post(action, data=fields)
    success = "modedit.php" not in post_resp.url

    return {"success": success, "cmid": cmid, "dry_run": False, "final_url": post_resp.url}


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
