#!/usr/bin/env python3
"""
moodle-cli — command-line client for Moodle administration.

Usage examples:
  moodle activity info     --site https://moodle.example.edu --cmid 42
  moodle activity set-end  --site https://moodle.example.edu --cmid 42 --date "2026-06-30 23:59"
  moodle activity set-end  --site https://moodle.example.edu --cmid 42 --date "2026-06-30 23:59" --dry-run
"""
from __future__ import annotations

import sys
from datetime import datetime

import click
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from moodle.session import MoodleSession
from moodle.activity import disable_activity_date, get_activity_dates, get_activity_html, get_activity_info, get_assign_summaries, get_module_raw_html, list_activities, set_activity_end_date, set_activity_html, set_activity_sep, set_activity_visibility
from moodle.course import list_courses

console = Console()

DATE_FORMATS = [
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
]


def parse_date(value: str) -> datetime:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise click.BadParameter(
        f"Unrecognised date format: {value!r}. "
        "Try YYYY-MM-DD HH:MM or DD/MM/YYYY HH:MM."
    )


# ---------------------------------------------------------------------------
# Shared options
# ---------------------------------------------------------------------------

def site_option(f):
    return click.option(
        "--site", "-s",
        required=True,
        envvar="MOODLE_SITE",
        help="Base URL of the Moodle site (or set MOODLE_SITE env var).",
    )(f)


def cookie_option(f):
    return click.option(
        "--cookie", "-c",
        required=True,
        envvar="MOODLE_COOKIE",
        help=(
            "Raw Cookie header string (or set MOODLE_COOKIE env var). "
            "Copy it from the Cookie: request header in browser DevTools."
        ),
    )(f)


def cmid_option(f):
    return click.option(
        "--cmid",
        required=True,
        type=int,
        help="Course module ID (the number after update= in the edit URL).",
    )(f)


# ---------------------------------------------------------------------------
# CLI groups
# ---------------------------------------------------------------------------

@click.group()
def main():
    """Moodle CLI — automate Moodle administration from the terminal."""


@main.group()
def course():
    """Commands for listing and managing courses."""


@main.group()
def activity():
    """Commands for managing course activities."""


@main.group()
def assign():
    """Commands for assignments."""


# ---------------------------------------------------------------------------
# assign list
# ---------------------------------------------------------------------------

@assign.command("list")
@site_option
@cookie_option
def assign_list(site, cookie):
    """List all assignments across starred courses with dates and grading info."""
    with console.status("Connecting to Moodle…"):
        try:
            session = MoodleSession.create(site=site, cookie_str=cookie)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    with console.status("Fetching starred courses…"):
        try:
            courses = list_courses(session, starred=True)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    if not courses:
        console.print("No starred courses found.")
        return

    assignments = []
    for c in courses:
        with console.status(f"Scanning {c['fullname']}…"):
            try:
                activities = list_activities(session, c["id"])
            except Exception:
                continue

            course_assigns = [
                {**a, "course_name": c["fullname"], "course_id": c["id"]}
                for a in activities
                if a["type"] == "assign" and "examen" not in a["name"].lower()
            ]
            if not course_assigns:
                continue

            try:
                summaries = get_assign_summaries(session, c["id"])
            except Exception:
                summaries = {}

            for a in course_assigns:
                s = summaries.get(a["cmid"], {"submitted": 0, "needs_grading": 0})
                a["_needs_grading"] = s["needs_grading"]
                a["submitted"] = str(s["submitted"])
                a["needs_grading"] = str(s["needs_grading"])

            assignments.extend(course_assigns)

    if not assignments:
        console.print("No assignments found in starred courses.")
        return

    now = datetime.now()

    for a in assignments:
        with console.status(f"Fetching dates for {a['name']}…"):
            try:
                dates = get_activity_dates(session, a["cmid"], ["duedate", "cutoffdate"])
                a["_cutoffdate"] = dates["cutoffdate"]
                a["duedate"] = dates["duedate"].strftime("%Y-%m-%d %H:%M") if dates["duedate"] else "—"
                a["cutoffdate"] = dates["cutoffdate"].strftime("%Y-%m-%d %H:%M") if dates["cutoffdate"] else "—"
            except Exception:
                a["_cutoffdate"] = None
                a["duedate"] = "—"
                a["cutoffdate"] = "—"

    def _status(a):
        ng = a["_needs_grading"]
        if ng == 0:
            return "\U0001f7e2"  # green
        cutoff = a["_cutoffdate"]
        if cutoff is not None and now <= cutoff:
            return "\U0001f7e0"  # orange
        return "\U0001f534"  # red

    table = Table(title=f"Assignments ({len(assignments)})")
    table.add_column("CMID", style="bold cyan", no_wrap=True)
    table.add_column("Course", style="bold")
    table.add_column("Name")
    table.add_column("Due date", no_wrap=True)
    table.add_column("Cutoff date", no_wrap=True)
    table.add_column("Submitted", no_wrap=True, justify="right")
    table.add_column("Needs grading", no_wrap=True, justify="right")
    table.add_column("", no_wrap=True)

    for a in assignments:
        table.add_row(
            str(a["cmid"]),
            a["course_name"],
            a["name"],
            a["duedate"],
            a["cutoffdate"],
            a["submitted"],
            a["needs_grading"],
            _status(a),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# sep-aula / sep-fora
# ---------------------------------------------------------------------------

@main.command("sep-aula")
@site_option
@cookie_option
def sep(site, cookie):
    """List AULA HABILITADA labels across all starred courses."""
    with console.status("Connecting to Moodle…"):
        try:
            session = MoodleSession.create(site=site, cookie_str=cookie)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    with console.status("Fetching starred courses…"):
        try:
            courses = list_courses(session, starred=True)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    if not courses:
        console.print("No starred courses found.")
        return

    matches = []
    for course in courses:
        with console.status(f"Scanning {course['fullname']}…"):
            try:
                activities = list_activities(session, course["id"])
            except Exception:
                continue
            for a in activities:
                if a["type"] == "label" and a["name"].upper().startswith("AULA HABILITADA"):
                    matches.append({**a, "course_name": course["fullname"]})

    if not matches:
        console.print("No 'AULA HABILITADA' labels found in starred courses.")
        return

    table = Table(title=f"AULA HABILITADA ({len(matches)})")
    table.add_column("CMID", style="bold cyan", no_wrap=True)
    table.add_column("Course", style="bold")
    table.add_column("Name")
    table.add_column("SEP", no_wrap=True)

    for a in matches:
        sep_str = "[green]✓[/green]" if a["visible"] else "[red]✗[/red]"
        table.add_row(
            str(a["cmid"]),
            a["course_name"],
            a["name"],
            sep_str,
        )

    console.print(table)
    console.print()

    hidden = [a for a in matches if not a["visible"]]
    if not hidden:
        console.print("[green]All labels are visible.[/green]")
        return

    for a in hidden:
        console.print(f"[dim]# {a['course_name']}[/dim]")
        console.print(f"moodle activity show --cmid {a['cmid']}")
        console.print()


@main.command("sep-fora")
@site_option
@cookie_option
def sep_fora(site, cookie):
    """List all forums across starred courses with their limit date."""
    with console.status("Connecting to Moodle…"):
        try:
            session = MoodleSession.create(site=site, cookie_str=cookie)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    with console.status("Fetching starred courses…"):
        try:
            courses = list_courses(session, starred=True)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    if not courses:
        console.print("No starred courses found.")
        return

    forums = []
    for course in courses:
        with console.status(f"Scanning {course['fullname']}…"):
            try:
                activities = list_activities(session, course["id"])
            except Exception:
                continue
            for a in activities:
                if a["type"] == "forum" and "anuncios" not in a["name"].lower():
                    forums.append({**a, "course_name": course["fullname"]})

    if not forums:
        console.print("No forums found in starred courses.")
        return

    now = datetime.now()

    for f in forums:
        with console.status(f"Fetching dates for {f['name']}…"):
            try:
                info = get_activity_info(session, f["cmid"])
                f["_end_date"] = info["end_date"]
                f["limit_date"] = info["end_date"].strftime("%Y-%m-%d %H:%M") if info["end_date"] else "—"
            except Exception:
                f["_end_date"] = None
                f["limit_date"] = "—"

    table = Table(title=f"Forums ({len(forums)})")
    table.add_column("CMID", style="bold cyan", no_wrap=True)
    table.add_column("Course", style="bold")
    table.add_column("Name")
    table.add_column("Visible", no_wrap=True)
    table.add_column("Limit date", no_wrap=True)
    table.add_column("SEP", no_wrap=True)

    def _is_sep_ok(f):
        is_sept = "septiembre" in f["name"].lower()
        if is_sept:
            return f["_end_date"] is None
        else:
            return f["_end_date"] is not None and f["_end_date"] < now

    for f in forums:
        visible_str = "[green]yes[/green]" if f["visible"] else "[red]no[/red]"
        sep_str = "[green]✓[/green]" if _is_sep_ok(f) else "[red]✗[/red]"
        table.add_row(
            str(f["cmid"]),
            f["course_name"],
            f["name"],
            visible_str,
            f["limit_date"],
            sep_str,
        )

    console.print(table)
    console.print()

    pending = [f for f in forums if not _is_sep_ok(f)]
    if not pending:
        console.print("[green]All forums are correctly configured.[/green]")
        return

    now_str = now.strftime("%Y-%m-%d %H:%M")
    current_course = None
    for f in pending:
        if f["course_name"] != current_course:
            current_course = f["course_name"]
            console.print(f"[bold]# {current_course}[/bold]")
        is_sept = "septiembre" in f["name"].lower()
        console.print(f"[dim]# {f['name']}[/dim]")
        if is_sept:
            console.print(f"moodle activity show --cmid {f['cmid']}")
        else:
            console.print(f'moodle activity set-end --cmid {f["cmid"]} --field cutoffdate --date "{now_str}"')
        console.print()


# ---------------------------------------------------------------------------
# sep-activities
# ---------------------------------------------------------------------------

@main.command("sep-activities")
@site_option
@cookie_option
def sep_activities(site, cookie):
    """List all assignments across starred courses with their due date and cutoff date."""
    with console.status("Connecting to Moodle…"):
        try:
            session = MoodleSession.create(site=site, cookie_str=cookie)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    with console.status("Fetching starred courses…"):
        try:
            courses = list_courses(session, starred=True)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    if not courses:
        console.print("No starred courses found.")
        return

    assignments = []
    for course in courses:
        with console.status(f"Scanning {course['fullname']}…"):
            try:
                activities = list_activities(session, course["id"])
            except Exception:
                continue
            for a in activities:
                if a["type"] == "assign" and "examen" not in a["name"].lower():
                    assignments.append({**a, "course_name": course["fullname"]})

    if not assignments:
        console.print("No assignments found in starred courses.")
        return

    year = datetime.now().year
    last_sunday = max(
        d for d in (datetime(year, 8, day) for day in range(25, 32))
        if d.weekday() == 6  # Sunday
    )
    target_due = last_sunday.replace(hour=23, minute=59)

    for a in assignments:
        with console.status(f"Fetching dates for {a['name']}…"):
            try:
                dates = get_activity_dates(session, a["cmid"], ["duedate", "cutoffdate"])
                a["_duedate"] = dates["duedate"]
                a["_cutoffdate"] = dates["cutoffdate"]
                a["duedate"] = dates["duedate"].strftime("%Y-%m-%d %H:%M") if dates["duedate"] else "—"
                a["cutoffdate"] = dates["cutoffdate"].strftime("%Y-%m-%d %H:%M") if dates["cutoffdate"] else "—"
            except Exception:
                a["_duedate"] = None
                a["_cutoffdate"] = None
                a["duedate"] = "—"
                a["cutoffdate"] = "—"

    table = Table(title=f"Assignments ({len(assignments)})")
    table.add_column("CMID", style="bold cyan", no_wrap=True)
    table.add_column("Course", style="bold")
    table.add_column("Name")
    table.add_column("Visible", no_wrap=True)
    table.add_column("Due date", no_wrap=True)
    table.add_column("Cutoff date", no_wrap=True)
    table.add_column("SEP", no_wrap=True)

    for a in assignments:
        visible_str = "[green]yes[/green]" if a["visible"] else "[red]no[/red]"
        due_ok = (
            a["_duedate"] is not None
            and a["_duedate"].year == target_due.year
            and a["_duedate"].month == target_due.month
            and a["_duedate"].day == target_due.day
            and a["_duedate"].hour == target_due.hour
            and a["_duedate"].minute == target_due.minute
        )
        sep_ok = due_ok and a["_cutoffdate"] is None
        sep_str = "[green]✓[/green]" if sep_ok else "[red]✗[/red]"
        table.add_row(
            str(a["cmid"]),
            a["course_name"],
            a["name"],
            visible_str,
            a["duedate"],
            a["cutoffdate"],
            sep_str,
        )

    console.print(table)
    console.print()

    pending = [a for a in assignments if not (
        a["_duedate"] is not None
        and a["_duedate"].year == target_due.year
        and a["_duedate"].month == target_due.month
        and a["_duedate"].day == target_due.day
        and a["_duedate"].hour == target_due.hour
        and a["_duedate"].minute == target_due.minute
        and a["_cutoffdate"] is None
    )]

    if not pending:
        console.print("[green]All assignments are correctly configured.[/green]")
        return

    current_course = None
    for a in pending:
        if a["course_name"] != current_course:
            current_course = a["course_name"]
            console.print(f"[bold]# {current_course}[/bold]")
        console.print(f"[dim]# {a['name']}[/dim]")
        console.print(f'moodle activity sep --cmid {a["cmid"]}')
        console.print()


# ---------------------------------------------------------------------------
# sep-quizzes
# ---------------------------------------------------------------------------

@main.command("sep-quizzes")
@site_option
@cookie_option
def sep_quizzes(site, cookie):
    """List all quizzes across starred courses with their close date."""
    with console.status("Connecting to Moodle…"):
        try:
            session = MoodleSession.create(site=site, cookie_str=cookie)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    with console.status("Fetching starred courses…"):
        try:
            courses = list_courses(session, starred=True)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    if not courses:
        console.print("No starred courses found.")
        return

    quizzes = []
    for course in courses:
        with console.status(f"Scanning {course['fullname']}…"):
            try:
                activities = list_activities(session, course["id"])
            except Exception:
                continue
            for a in activities:
                if a["type"] == "quiz" and "examen" not in a["name"].lower():
                    quizzes.append({**a, "course_name": course["fullname"]})

    if not quizzes:
        console.print("No quizzes found in starred courses.")
        return

    year = datetime.now().year
    last_sunday = max(
        d for d in (datetime(year, 8, day) for day in range(25, 32))
        if d.weekday() == 6  # Sunday
    )
    target = last_sunday.replace(hour=23, minute=59)

    for q in quizzes:
        with console.status(f"Fetching dates for {q['name']}…"):
            try:
                dates = get_activity_dates(session, q["cmid"], ["timeclose"])
                q["_timeclose"] = dates["timeclose"]
                q["timeclose"] = dates["timeclose"].strftime("%Y-%m-%d %H:%M") if dates["timeclose"] else "—"
            except Exception:
                q["_timeclose"] = None
                q["timeclose"] = "—"

    table = Table(title=f"Quizzes ({len(quizzes)})")
    table.add_column("CMID", style="bold cyan", no_wrap=True)
    table.add_column("Course", style="bold")
    table.add_column("Name")
    table.add_column("Visible", no_wrap=True)
    table.add_column("Close date", no_wrap=True)
    table.add_column("SEP", no_wrap=True)

    def _is_ok(q):
        tc = q["_timeclose"]
        return (
            tc is not None
            and tc.year == target.year
            and tc.month == target.month
            and tc.day == target.day
            and tc.hour == target.hour
            and tc.minute == target.minute
        )

    for q in quizzes:
        visible_str = "[green]yes[/green]" if q["visible"] else "[red]no[/red]"
        sep_str = "[green]✓[/green]" if _is_ok(q) else "[red]✗[/red]"
        table.add_row(
            str(q["cmid"]),
            q["course_name"],
            q["name"],
            visible_str,
            q["timeclose"],
            sep_str,
        )

    console.print(table)
    console.print()

    pending = [q for q in quizzes if not _is_ok(q)]
    if not pending:
        console.print("[green]All quizzes are correctly configured.[/green]")
        return

    current_course = None
    for q in pending:
        if q["course_name"] != current_course:
            current_course = q["course_name"]
            console.print(f"[bold]# {current_course}[/bold]")
        console.print(f"[dim]# {q['name']}[/dim]")
        console.print(f'moodle activity sep --cmid {q["cmid"]}')
        console.print()


# ---------------------------------------------------------------------------
# course list
# ---------------------------------------------------------------------------

@course.command("list")
@site_option
@cookie_option
@click.option(
    "--starred",
    is_flag=True,
    default=False,
    help="Show only courses marked as starred (favourites).",
)
def course_list(site, cookie, starred):
    """List all courses you are enrolled in."""
    with console.status("Connecting to Moodle…"):
        try:
            session = MoodleSession.create(site=site, cookie_str=cookie)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    with console.status("Fetching course list…"):
        try:
            courses = list_courses(session, starred=starred)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    if not courses:
        console.print("No starred courses found." if starred else "No courses found.")
        return

    title = f"Starred courses ({len(courses)})" if starred else f"Courses ({len(courses)})"
    table = Table(title=title)
    table.add_column("ID", style="bold cyan", no_wrap=True)
    table.add_column("Short name", style="bold")
    table.add_column("Full name")
    table.add_column("Category", style="dim")

    for c in courses:
        table.add_row(
            str(c["id"]),
            c["shortname"] or "—",
            c["fullname"],
            c["category"] or "—",
        )

    console.print(table)


# ---------------------------------------------------------------------------
# activity list
# ---------------------------------------------------------------------------

@activity.command("list")
@site_option
@cookie_option
@click.option(
    "--course",
    "course_id",
    required=True,
    type=int,
    help="Course ID to list activities for.",
)
@click.option(
    "--section",
    "section_name",
    default=None,
    help="Filter by section name (e.g. --section General).",
)
@click.option(
    "--type",
    "mod_type",
    default=None,
    help="Filter by module type (e.g. --type forum).",
)
def activity_list(site, cookie, course_id, section_name, mod_type):
    """List all activities in a course."""
    with console.status("Connecting to Moodle…"):
        try:
            session = MoodleSession.create(site=site, cookie_str=cookie)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    with console.status(f"Fetching activities for course {course_id}…"):
        try:
            activities = list_activities(session, course_id)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    if section_name:
        activities = [a for a in activities if a["section"].lower() == section_name.lower()]
    if mod_type:
        activities = [a for a in activities if a["type"].lower() == mod_type.lower()]

    if not activities:
        console.print("No activities found.")
        return

    title = f"Activities in course {course_id} — {section_name} ({len(activities)})" if section_name else f"Activities in course {course_id} ({len(activities)})"
    table = Table(title=title)
    table.add_column("CMID", style="bold cyan", no_wrap=True)
    table.add_column("Type", style="bold")
    table.add_column("Name")
    table.add_column("Section", style="dim")
    table.add_column("Visible", no_wrap=True)

    for a in activities:
        visible_str = "[green]yes[/green]" if a["visible"] else "[red]no[/red]"
        table.add_row(
            str(a["cmid"]),
            a["type"],
            a["name"],
            a["section"] or "—",
            visible_str,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# activity disable-date
# ---------------------------------------------------------------------------

@activity.command("disable-date")
@site_option
@cookie_option
@cmid_option
@click.option("--field", required=True, help="Date field to disable (e.g. cutoffdate).")
def activity_disable_date(site, cookie, cmid, field):
    """Disable a date field on an activity without changing its value."""
    with console.status("Connecting to Moodle…"):
        try:
            session = MoodleSession.create(site=site, cookie_str=cookie)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    with console.status(f"Disabling {field} for cmid={cmid}…"):
        try:
            disable_activity_date(session, cmid, field)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    console.print(f"[green]Success![/green] {field} disabled for cmid={cmid}.")


# ---------------------------------------------------------------------------
# activity show / hide
# ---------------------------------------------------------------------------

@activity.command("show")
@site_option
@cookie_option
@cmid_option
def activity_show(site, cookie, cmid):
    """Make a course module visible."""
    with console.status("Connecting to Moodle…"):
        try:
            session = MoodleSession.create(site=site, cookie_str=cookie)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    with console.status(f"Showing cmid={cmid}…"):
        set_activity_visibility(session, cmid, visible=True)

    console.print(f"[green]Success![/green] cmid={cmid} is now visible.")


@activity.command("hide")
@site_option
@cookie_option
@cmid_option
def activity_hide(site, cookie, cmid):
    """Hide a course module from students."""
    with console.status("Connecting to Moodle…"):
        try:
            session = MoodleSession.create(site=site, cookie_str=cookie)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    with console.status(f"Hiding cmid={cmid}…"):
        set_activity_visibility(session, cmid, visible=False)

    console.print(f"[green]Success![/green] cmid={cmid} is now hidden.")


# ---------------------------------------------------------------------------
# activity debug-html
# ---------------------------------------------------------------------------

@activity.command("debug-html")
@site_option
@cookie_option
@cmid_option
@click.option("--course", "course_id", required=True, type=int, help="Course ID.")
def activity_debug_html(site, cookie, cmid, course_id):
    """Print the raw HTML of a module element (for debugging visibility detection)."""
    with console.status("Connecting to Moodle…"):
        try:
            session = MoodleSession.create(site=site, cookie_str=cookie)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    with console.status(f"Fetching module HTML for cmid={cmid}…"):
        try:
            html = get_module_raw_html(session, course_id, cmid)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    console.print(html)


# ---------------------------------------------------------------------------
# activity html
# ---------------------------------------------------------------------------

@activity.command("html")
@site_option
@cookie_option
@cmid_option
def activity_html(site, cookie, cmid):
    """Print the raw HTML content of a label/text activity."""
    with console.status("Connecting to Moodle…"):
        try:
            session = MoodleSession.create(site=site, cookie_str=cookie)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    with console.status(f"Fetching HTML for cmid={cmid}…"):
        try:
            html = get_activity_html(session, cmid)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    console.print(html)


# ---------------------------------------------------------------------------
# activity set-html
# ---------------------------------------------------------------------------

@activity.command("set-html")
@site_option
@cookie_option
@cmid_option
@click.option(
    "--html",
    "html_str",
    default=None,
    help="New HTML content as a string.",
)
@click.option(
    "--file",
    "html_file",
    default=None,
    type=click.Path(exists=True, readable=True),
    help="Path to a file containing the new HTML content.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be sent without actually submitting.",
)
def activity_set_html(site, cookie, cmid, html_str, html_file, dry_run):
    """Replace the HTML content of a label/text activity."""
    if not html_str and not html_file:
        console.print("[red]Error:[/red] Provide --html or --file.")
        sys.exit(1)

    if html_file:
        with open(html_file) as f:
            new_html = f.read()
    else:
        new_html = html_str

    with console.status("Connecting to Moodle…"):
        try:
            session = MoodleSession.create(site=site, cookie_str=cookie)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    label = "[yellow]DRY RUN[/yellow] — " if dry_run else ""
    with console.status(f"{label}Updating HTML for cmid={cmid}…"):
        try:
            result = set_activity_html(session, cmid, new_html, dry_run=dry_run)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    if dry_run:
        console.print(f"[yellow]DRY RUN[/yellow] — would update HTML content for cmid={cmid}.")
        console.print("No changes were made.")
        return

    if result["success"]:
        console.print(f"[green]Success![/green] HTML content updated for cmid={cmid}.")
    else:
        console.print(
            f"[red]Warning:[/red] Form submitted but Moodle did not redirect as expected. "
            f"Final URL: {result.get('final_url')}\n"
            "The change may not have been applied. Check Moodle directly."
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# activity info
# ---------------------------------------------------------------------------

@activity.command("info")
@site_option
@cookie_option
@cmid_option
def activity_info(site, cookie, cmid):
    """Show current settings for an activity (including end date)."""
    with console.status("Connecting to Moodle…"):
        try:
            session = MoodleSession.create(site=site, cookie_str=cookie)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    with console.status(f"Fetching activity cmid={cmid}…"):
        try:
            info = get_activity_info(session, cmid)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    table = Table(title=f"Activity info — cmid {cmid}", show_header=False)
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")

    table.add_row("Name", str(info["name"]))
    table.add_row("Type", str(info["type"]))
    table.add_row("End date field", str(info["end_date_field"] or "(none detected)"))
    end = info["end_date"]
    table.add_row(
        "Current end date",
        end.strftime("%Y-%m-%d %H:%M") if end else "(not set)",
    )

    console.print(table)


# ---------------------------------------------------------------------------
# activity set-end
# ---------------------------------------------------------------------------

@activity.command("set-end")
@site_option
@cookie_option
@cmid_option
@click.option(
    "--date", "-d",
    "date_str",
    required=True,
    help='New end date/time, e.g. "2026-06-30 23:59".',
)
@click.option(
    "--field",
    default=None,
    help='Date field to set (e.g. cutoffdate, duedate). Auto-detected if not given.',
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Parse and show what would be sent without actually submitting.",
)
def activity_set_end(site, cookie, cmid, date_str, field, dry_run):
    """Change the end date of an activity."""
    try:
        new_date = parse_date(date_str)
    except click.BadParameter as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    with console.status("Connecting to Moodle…"):
        try:
            session = MoodleSession.create(site=site, cookie_str=cookie)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    label = "[yellow]DRY RUN[/yellow] — " if dry_run else ""
    with console.status(f"{label}Updating cmid={cmid}…"):
        try:
            result = set_activity_end_date(
                session, cmid, new_date, dry_run=dry_run, field=field
            )
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    if dry_run:
        console.print(f"[yellow]DRY RUN[/yellow] — would set [bold]{result['end_date_field']}[/bold] "
                      f"to [bold]{new_date.strftime('%Y-%m-%d %H:%M')}[/bold] for cmid={cmid}.")
        console.print("No changes were made.")
        return

    if result["success"]:
        console.print(
            f"[green]Success![/green] End date for cmid={cmid} "
            f"([bold]{result['end_date_field']}[/bold]) "
            f"set to [bold]{new_date.strftime('%Y-%m-%d %H:%M')}[/bold]."
        )
    else:
        console.print(
            f"[red]Warning:[/red] The form was submitted but Moodle did not redirect "
            f"as expected. Final URL: {result.get('final_url')}\n"
            "The change may not have been applied. Check Moodle directly."
        )
        if result.get("_history"):
            console.print("[dim]HTTP history:[/dim]")
            for status, url in result["_history"]:
                console.print(f"  [dim]{status}  {url}[/dim]")
        html = result.get("_response_html")
        if html:
            import tempfile, os
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".html", prefix="moodle_debug_", delete=False
            ) as f:
                f.write(html)
                debug_path = f.name
            console.print(f"[dim]Response HTML saved to: {debug_path}[/dim]")
            console.print(f"[dim]Open with: open {debug_path}[/dim]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# activity sep
# ---------------------------------------------------------------------------

@activity.command("sep")
@site_option
@cookie_option
@cmid_option
@click.option(
    "--date", "-d",
    "date_str",
    default=None,
    help='New due date, e.g. "2026-08-30 23:59". Defaults to last Sunday of August at 23:59.',
)
def activity_sep(site, cookie, cmid, date_str):
    """Disable cutoffdate and set duedate in one step (SEP shortcut)."""
    if date_str:
        try:
            new_date = parse_date(date_str)
        except click.BadParameter as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)
    else:
        year = datetime.now().year
        last_sunday = max(
            d for d in (datetime(year, 8, day) for day in range(25, 32))
            if d.weekday() == 6
        )
        new_date = last_sunday.replace(hour=23, minute=59)

    with console.status("Connecting to Moodle…"):
        try:
            session = MoodleSession.create(site=site, cookie_str=cookie)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    with console.status(f"Updating cmid={cmid}…"):
        try:
            result = set_activity_sep(session, cmid, new_date)
        except RuntimeError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

    if result["success"]:
        console.print(
            f"[green]Success![/green] cmid={cmid}: "
            f"end date set to [bold]{new_date.strftime('%Y-%m-%d %H:%M')}[/bold]."
        )
    else:
        console.print(
            f"[red]Warning:[/red] The form was submitted but Moodle did not redirect "
            f"as expected. Final URL: {result.get('final_url')}\n"
            "The change may not have been applied. Check Moodle directly."
        )
        if result.get("_history"):
            console.print("[dim]HTTP history:[/dim]")
            for status, url in result["_history"]:
                console.print(f"  [dim]{status}  {url}[/dim]")
        html = result.get("_response_html")
        if html:
            import tempfile
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".html", prefix="moodle_debug_", delete=False
            ) as f:
                f.write(html)
                debug_path = f.name
            console.print(f"[dim]Response HTML saved to: {debug_path}[/dim]")
            console.print(f"[dim]Open with: open {debug_path}[/dim]")
        sys.exit(1)


if __name__ == "__main__":
    main()
