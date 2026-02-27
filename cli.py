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
from moodle.activity import get_activity_info, set_activity_end_date

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
        default=None,
        envvar="MOODLE_COOKIE",
        help=(
            "Raw Cookie header string. "
            "If omitted, cookies are read from Chrome/Firefox automatically."
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
def activity():
    """Commands for managing course activities."""


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
    "--dry-run",
    is_flag=True,
    default=False,
    help="Parse and show what would be sent without actually submitting.",
)
def activity_set_end(site, cookie, cmid, date_str, dry_run):
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
                session, cmid, new_date, dry_run=dry_run
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
        sys.exit(1)


if __name__ == "__main__":
    main()
