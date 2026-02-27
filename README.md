# moodle-client

A command-line client for automating repetitive Moodle administration tasks.

No API key required — it reuses your existing browser session.

---

## How it works

Moodle's web interface is a set of HTML forms protected by a CSRF token (`sesskey`). This tool:

1. Extracts your session cookies from Chrome or Firefox automatically
2. Scrapes the `sesskey` from the Moodle home page
3. Fetches activity edit forms, modifies the relevant fields, and submits them — exactly what your browser does, but from the terminal

---

## Requirements

- Python 3.10+
- Chrome or Firefox with an active Moodle session
- `pip`

---

## Installation

```bash
git clone git@github.com:javiervidal/moodle-client.git
cd moodle-client
pip install -e .
```

---

## Usage

### Set an environment variable to avoid repeating the site URL

```bash
export MOODLE_SITE=https://moodle.example.edu
```

### Show current settings for an activity

```bash
moodle activity info --cmid 42
```

Example output:

```
┌─────────────────────────────┐
│   Activity info — cmid 42   │
├──────────────────┬──────────┤
│ Name             │ Exam 1   │
│ Type             │ quiz     │
│ End date field   │ timeclose│
│ Current end date │ 2026-05-31 23:59 │
└──────────────────┴──────────┘
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
moodle activity info
  --site, -s    Base URL of the Moodle site  [env: MOODLE_SITE]
  --cmid        Course module ID (the number after update= in the edit URL)
  --cookie, -c  Raw Cookie header string (auto-detected from browser if omitted)
                [env: MOODLE_COOKIE]

moodle activity set-end
  --site, -s    Base URL of the Moodle site  [env: MOODLE_SITE]
  --cmid        Course module ID
  --date, -d    New end date/time, e.g. "2026-06-30 23:59"
  --dry-run     Show what would be sent without submitting
  --cookie, -c  Raw Cookie header string  [env: MOODLE_COOKIE]
```

### Accepted date formats

| Format | Example |
|---|---|
| `YYYY-MM-DD HH:MM` | `2026-06-30 23:59` |
| `YYYY-MM-DD` | `2026-06-30` (time defaults to 00:00) |
| `DD/MM/YYYY HH:MM` | `30/06/2026 23:59` |
| `DD/MM/YYYY` | `30/06/2026` |

---

## How to find the cmid

Open the activity in Moodle and click the edit (pencil) icon. The URL will contain `?update=42` — that number is the cmid.

---

## Troubleshooting

**"No cookies found for … in Chrome/Firefox"**
Make sure you are logged in to Moodle in Chrome or Firefox, and that the browser is not sandboxed. Alternatively, open DevTools → Network → copy the `Cookie` header from any Moodle request and pass it with `--cookie "…"` or set `MOODLE_COOKIE`.

**"Could not extract sesskey"**
Your session may have expired. Log in again in the browser.

**"No supported end-date field found"**
The activity type may use a field name not yet in the detection list. Run with `--dry-run` and check the `_fields` output, then open an issue.

---

## Project structure

```
moodle-client/
├── moodle/
│   ├── __init__.py
│   ├── session.py      # Cookie extraction, sesskey, HTTP session
│   └── activity.py     # Activity form parsing and submission
├── cli.py              # Click-based CLI entry point
├── PLAN.md             # Roadmap and planned features
└── pyproject.toml
```

---

## Supported activity types

End-date field detection covers:

| Field | Activity types |
|---|---|
| `timeclose` | Quiz, Choice, Feedback, Lesson |
| `duedate` / `cutoffdate` | Assignment |
| `timeend` | Generic fallback |

---

## License

MIT
