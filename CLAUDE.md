# Project rules

- Never create git commits. The user stages files and commits manually.

# Architecture

- `moodle/session.py` — Cookie auth, sesskey extraction, HTTP session wrapper
- `moodle/course.py` — Course listing
- `moodle/activity.py` — Activity form parsing and submission
- `moodle/cli.py` — Click-based CLI entry point

# Moodle form submission

Moodle forms rely on client-side JavaScript to modify fields before submission. Since we parse raw HTML without running JS, `_prepare_for_submission()` in `activity.py` cleans up parsed fields to match browser behavior:

- Removes date-selector groups whose `[enabled]` checkbox is `"0"` (JS disables these)
- Sets `availabilityconditionsjson` to valid empty JSON when blank (JS populates this)
- Removes the plugin-injected `action` hidden field
- Keeps only `submitbutton2` (browsers only send the clicked button)
- Removes the `unlockcompletion` button
