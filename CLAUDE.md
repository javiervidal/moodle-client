# CLAUDE

## Project rules

- Never create git commits. The user stages files and commits manually.

## Architecture

- `moodle/session.py` — Cookie auth, sesskey extraction, HTTP session wrapper
- `moodle/course.py` — Course listing
- `moodle/activity.py` — Activity form parsing and submission
- `moodle/cli.py` — Click-based CLI entry point

## Moodle form submission

Moodle forms rely on client-side JavaScript to modify fields before submission. Since we parse raw HTML without running JS, `_prepare_for_submission()` in `activity.py` cleans up parsed fields to match browser behavior:

- Unchecked checkboxes are omitted entirely (browsers never submit them); code must check `!= "1"` (not `== "0"`) to detect disabled state since the key may be absent
- Removes date/duration-selector groups whose `[enabled]` checkbox is absent or `"0"`
- Sets `availabilityconditionsjson` to valid empty JSON when blank (JS populates this)
- Removes SEB detail fields when `seb_requiresafeexambrowser` is `"0"`
- Removes the plugin-injected `action` hidden field and `boundary_add_fields` button
- Removes `groupingid` when `groupmode` is `"0"`
- Keeps only `submitbutton2` (browsers only send the clicked button)
- Removes the `unlockcompletion` button

## Assign commands

- `assign list` — Lists all assignments (excl. exams) across starred courses with duedate, cutoffdate, submitted count, needs grading count, and a status dot. Submission/grading data is scraped from `/mod/assign/index.php?id=<course_id>` (one request per course). Dates come from the edit form via `get_activity_dates()` (one request per assignment).

## SEP commands

The `sep-*` commands configure courses for the September exam period, operating on starred courses:

- `sep-aula` — AULA HABILITADA labels: green `✓` if visible
- `sep-fora` — Forums (excl. announcements): regular forums green `✓` if limit date in the past; "septiembre" forums green `✓` if no limit date
- `sep-activities` — Assignments (excl. exams): green `✓` if duedate matches target and cutoffdate disabled
- `sep-quizzes` — Quizzes (excl. exams): green `✓` if timeclose matches target
- `activity sep` — Single-activity shortcut: sets duedate/timeclose and disables cutoffdate (assignments only)
