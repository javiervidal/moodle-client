# moodle-client

A command-line client for automating repetitive Moodle administration tasks.

No API key required — it authenticates using a cookie copied from your browser.

---

## How it works

Moodle's web interface is a set of HTML forms protected by a CSRF token (`sesskey`). This tool:

1. Authenticates using a cookie copied from your browser DevTools
2. Scrapes the `sesskey` from the Moodle home page
3. Fetches and submits Moodle forms — exactly what your browser does, but from the terminal

---

## Requirements

- Python 3.10+
- A Moodle account with editing rights
- `pip`

---

## Installation

```bash
git clone git@github.com:javiervidal/moodle-client.git
cd moodle-client
pip install -e .
```

---

## Authentication

This tool does not extract cookies from your browser automatically. You need to copy the session cookie once from DevTools:

1. Log in to Moodle in your browser
2. Open DevTools → **Network** tab → reload the page
3. Click any request to your Moodle site
4. Under **Request Headers**, find the `Cookie:` line
5. Copy the value of `MoodleSession…` (you only need that one cookie)

Then export it as an environment variable:

```bash
export MOODLE_SITE=https://moodle.example.edu
export MOODLE_COOKIE="MoodleSessionXXX=abc123"
```

Add both lines to your `~/.zshrc` (or `~/.bashrc`) to persist them across terminal sessions. You will need to refresh `MOODLE_COOKIE` when your Moodle session expires.

---

## Usage

### List all your courses

```bash
moodle course list
```

### List only starred courses

```bash
moodle course list --starred
```

### Show current settings for an activity

```bash
moodle activity info --cmid 42
```

### Change the end date of an activity

```bash
moodle activity set-end --cmid 42 --date "2026-06-30 23:59"
```

### Preview without submitting (dry run)

```bash
moodle activity set-end --cmid 42 --date "2026-06-30 23:59" --dry-run
```

### All options

```
moodle course list
  --site, -s    Base URL of the Moodle site  [env: MOODLE_SITE]
  --cookie, -c  Raw Cookie header string  [env: MOODLE_COOKIE]
  --starred     Show only courses marked as starred (favourites)

moodle activity info
  --site, -s    Base URL of the Moodle site  [env: MOODLE_SITE]
  --cmid        Course module ID (the number after update= in the edit URL)
  --cookie, -c  Raw Cookie header string  [env: MOODLE_COOKIE]

moodle activity set-end
  --site, -s    Base URL of the Moodle site  [env: MOODLE_SITE]
  --cmid        Course module ID
  --date, -d    New end date/time, e.g. "2026-06-30 23:59"
  --dry-run     Show what would be sent without submitting
  --cookie, -c  Raw Cookie header string  [env: MOODLE_COOKIE]
```

### Accepted date formats

| Format             | Example                               |
| ------------------ | ------------------------------------- |
| `YYYY-MM-DD HH:MM` | `2026-06-30 23:59`                    |
| `YYYY-MM-DD`       | `2026-06-30` (time defaults to 00:00) |
| `DD/MM/YYYY HH:MM` | `30/06/2026 23:59`                    |
| `DD/MM/YYYY`       | `30/06/2026`                          |

---

## September configuration

Commands for configuring courses for the September exam period. All commands operate on your starred courses.

### sep-aula

Lists all label modules named `AULA HABILITADA` across starred courses, showing their current visibility, and prints ready-to-run hide/show commands for each one.

```bash
moodle sep-aula
```

### sep-forum

Lists all forums (excluding announcements) across starred courses with their visibility and cutoff date, and prints ready-to-run hide/show/set-date commands grouped by course.

```bash
moodle sep-forum
```

### sep-activities

Lists all assignments (excluding exams) across starred courses with their due date, cutoff date, and a SEP status column (green `✓` if duedate is last Sunday of August at 23:59 and cutoffdate is disabled, red `✗` otherwise). Prints ready-to-run `activity sep` commands for unconfigured assignments.

```bash
moodle sep-activities
```

### activity sep

Disables cutoffdate and sets duedate to the last Sunday of August at 23:59 in a single form submission. Optionally accepts `--date` to override the default date.

```bash
moodle activity sep --cmid 42
moodle activity sep --cmid 42 --date "2026-08-30 23:59"
```

---

## How to find the cmid

Open the activity in Moodle and click the edit (pencil) icon. The URL will contain `?update=42` — that number is the cmid.

---

## Troubleshooting

**"Could not extract sesskey"**
Your session has expired. Copy a fresh `MoodleSession…` cookie from DevTools and update `MOODLE_COOKIE`.

**"No supported end-date field found"**
The activity type may use a field name not yet in the detection list. Run with `--dry-run` and check the `_fields` output, then open an issue.

---

## Project structure

```
moodle-client/
├── moodle/
│   ├── __init__.py
│   ├── session.py      # Cookie auth, sesskey, HTTP session
│   ├── course.py       # Course listing
│   ├── activity.py     # Activity form parsing and submission
│   └── cli.py          # Click-based CLI entry point
├── PLAN.md             # Roadmap and planned features
└── pyproject.toml
```

---

## Supported activity types

End-date field detection covers:

| Field                    | Activity types                 |
| ------------------------ | ------------------------------ |
| `timeclose`              | Quiz, Choice, Feedback, Lesson |
| `duedate` / `cutoffdate` | Assignment                     |
| `timeend`                | Generic fallback               |

---

## License

MIT
