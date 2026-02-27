# moodle-client — plan & roadmap

This document tracks what has been built, what is in progress, and what is planned.

---

## Phase 1 — Foundation (done)

- [x] Project scaffold (`pyproject.toml`, `moodle/` package, `cli.py`)
- [x] **Session layer** (`moodle/session.py`)
  - Auto-extract cookies from Chrome / Firefox via `browser_cookie3`
  - Manual fallback via `--cookie` flag or `MOODLE_COOKIE` env var
  - Scrape `sesskey` CSRF token from Moodle home page
  - Thin `get` / `post` wrappers with automatic base-URL resolution
- [x] **Activity module** (`moodle/activity.py`)
  - Fetch and parse `modedit.php` form (all inputs, selects, textareas)
  - Auto-detect end-date field (`timeclose`, `duedate`, `cutoffdate`, `timeend`)
  - Override date selector fields and POST back
  - `--dry-run` mode (shows payload without submitting)
- [x] **CLI** (`cli.py`)
  - `moodle activity info` — display current activity settings
  - `moodle activity set-end` — change end date
  - `MOODLE_SITE` / `MOODLE_COOKIE` env-var support
  - Rich terminal output

---

## Phase 2 — More activity operations

- [ ] `moodle activity set-start` — change the start/open date of an activity
- [ ] `moodle activity enable` / `disable` — toggle activity visibility
- [ ] `moodle activity set-dates` — set both open and close dates in one call
- [ ] Support for **Assignment** (`duedate`, `cutoffdate`) with flat timestamp fields
  (Assignment stores dates as Unix timestamps, not `[day][month]…` selectors)
- [ ] Support for **Lesson** time limit fields
- [ ] Batch update: read a CSV of (cmid, new_date) and apply all changes

---

## Phase 3 — Course discovery

> Goal: avoid having to look up cmids by hand in the browser.

- [ ] `moodle course list` — list all courses the user can edit
- [ ] `moodle course activities --course-id <id>` — list all activities in a course
  (name, type, cmid, current open/close dates)
- [ ] `moodle course sections --course-id <id>` — list sections with their activities
- [ ] Fuzzy-match activities by name (so you can say `--name "Exam 1"` instead of `--cmid 42`)

---

## Phase 4 — Bulk operations

- [ ] CSV input mode: `moodle activity set-end --from-csv dates.csv`
  - CSV columns: `cmid`, `date` (and optionally `site`)
- [ ] JSON output mode: `moodle --json activity info --cmid 42`
  - For piping into other tools / scripts
- [ ] `--confirm` / `--yes` flags for unattended scripting
- [ ] Progress bar via Rich for bulk operations

---

## Phase 5 — Configuration file

> Goal: avoid passing `--site` on every command.

- [ ] `~/.config/moodle-client/config.toml` with default site, cookie strategy, etc.
- [ ] `moodle config set-site <url>`
- [ ] Support for multiple Moodle instances (profiles)

---

## Phase 6 — Robustness & maintenance

- [ ] Unit tests for form parsing (fixture HTML from real Moodle pages)
- [ ] Integration test mode (real Moodle, gated on env var)
- [ ] Detect Moodle version from page metadata and adapt field names accordingly
- [ ] Better error messages when Moodle returns a validation error on the form
- [ ] Session caching: store extracted sesskey to avoid a round-trip on every command
- [ ] `--verbose` / `--debug` flag to print raw HTTP traffic

---

## Technical notes

### Why no API key?

Moodle has an official REST API, but it requires an administrator to generate a token and
enable specific web-service functions — permissions that are not always granted to
course-level administrators. This client works at the HTTP form level, so it only needs
the same access you already have in the browser.

### sesskey / CSRF

Every mutating Moodle request requires a `sesskey` parameter. It is embedded in every
page as a JS variable (`"sesskey":"…"`) and in hidden form inputs. We extract it once
per session from the home page.

### Date field formats

Moodle date-selector widgets decompose a timestamp into five HTML `<select>` elements:
`{field}[day]`, `{field}[month]`, `{field}[year]`, `{field}[hour]`, `{field}[minute]`.
Assignment's `duedate` is an exception: it is stored as a Unix timestamp and submitted
as a flat integer — Phase 2 will handle this case separately.

### Form parsing strategy

We parse the entire `mform1` form rather than targeting specific fields, then overlay
only the fields we want to change. This means unknown fields (rich-text editors,
Filepicker widgets, custom fields) are passed through unchanged, reducing the risk of
accidentally corrupting an activity's settings.
