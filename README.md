# EscalationCache (Python alpha)

Run from inside this folder:

    python app.py

or double-click `run.bat`.

First run creates `data\` alongside the scripts (seeded with 4 sample entries,
one of which has a prior version, plus 1 tool). Identity is
`getpass.getuser()` so each AD account gets its own 5 starting Influence.
Delete `data\` to reset to a clean slate.

Stdlib only. Target runtime is Python 3.12.1 with Tcl/Tk 8.6.x.

This is the v0.2.4 build (window title: "EscalationCache Alpha Test v0.2.4").

## Interface

One window. Slate-charcoal theme with cyan accents on the brand wordmark and
your Influence balance. The balance flashes briefly each time it changes so
you can see the economy move.

Navigation is a canvas state machine. No popups for content, only for
confirmations and results:

* **Home** is a single-pane column list, newest first:
  CONTRIBUTION (bounded near example length, long titles truncate with an ellipsis) | STATUS | CREATED | IMPROVED | VALIDATED | SHARE.
  STATUS shows named tag chips (e.g. `stale` plus `citation`). Hovering a row
  lightens it and turns the title cyan. Clicking opens the contribution.
  The header row holds the wordmark, home button, a wide search field, the
  Search button, and the Influence chip. With no search term, the list shows
  the 6 most recent contributions; search to reach the rest.
* **Contribution view** (after spend) fills the canvas. Back button top-left,
  Versions button and Influence chip top-right. The meta line shows the
  lifecycle: `created by X` alone for an untouched v1, or
  `created by X, improved by Y` once it has been improved. Action row pinned
  at the bottom: Improve (primary), Validate, Citation request.
* **Editor** (Pioneer or Improve) has a title field, body text widget, and an
  aids sidebar (Step / Code / Disclaimer). Contribute and Cancel are pinned
  at the bottom with a "+N influence" indicator.
* **Versions** is a card list of prior versions; opening one costs Influence
  based on its age.

`Esc` or the back button pops one level. On Home with text in the search
field, `Esc` clears the field instead.

## Body format (block markers)

Block tags must be on their own line, exactly, with no leading whitespace or
trailing content:

    [step]
    Open Indexing Options
    [/step]

    [code]
    net stop spooler
    [/code]

    [disclaimer]
    Only works on corp wifi.
    [/disclaimer]

The aids sidebar wraps your highlighted text in the chosen tag, or inserts an
empty block at the cursor if nothing is selected. The `[disclaimer]` aid seeds
default "Use at your own risk." text you can edit.

## Tags

* **submitted** (grey outline): contributed, not yet validated.
* **validated** (green): someone other than the current author vouched it works.
* **stale** (amber): computed, never stored. A validated contribution older
  than 180 days since its last validation shows as stale.
* **citation** (yellow flag): a separate, optional chip; someone flagged it as
  possibly wrong or unverified. It coexists with the status tag.

## Economy (tune in `config.py`)

* Pioneer +3, Improve +3.
* Citation request 0 (free, no farm incentive); clearing your own flag 0.
* Validate someone else's work pays `min(8, 1 + days_since_validation // 30)`
  plus 2 if it is flagged. Older and flagged work pays more.
* **Self-validation is blocked**: you cannot validate a version you authored.
  Once someone else improves it, you can validate their version.
* Return bonus +1 after 7+ idle days, lifetime cap 10. Start at 5.
* Access cost: `min(8, max(1, base + days_since_validation // 60))`, where
  base is 1 (submitted), 2 (validated), 3 (stale).
* **Free window**: after you pay to open a contribution, it is free to reopen
  for 24 hours. Creating a new contribution opens the same window, so you can
  reopen and edit what you just wrote. The clock does not reset on reopen. The
  SHARE column shows `0 INF (next Nh)` on one line while active. Prior versions
  get their own 24h grace per version. Tools are excluded.

## Citation lifecycle

A contribution carries at most one outstanding citation (`cited_by` is a
single user). The Citation request button:

* On an unflagged entry: confirms what a citation means, then sets the flag
  with your name and today's date.
* On an entry **you** flagged: relabels to **Clear citation** and removes your
  own flag (no confirm, no cost).
* On an entry someone else flagged: tells you who flagged it.

**Both Improve and Validate clear an open citation.** Improving rewrites the
body and resolves the concern by definition; validating means someone vouched
the current body is good as-is. Once cleared, if something is still wrong the
next person raises a fresh citation rather than leaning on a stale one.

## Search

Matches the title, the current body, and every prior version's body, then
returns each contribution once at its current version. A keyword that lived
only in an old version still surfaces the contribution (current version
shown, old wording reachable via Versions). No duplicate rows per version.

## Known alpha constraints (deliberate)

* No login; identity is the Windows user.
* No tier gating on tools; if you can afford it you can run it.
* Tools are placeholders; running one is simulated. The Tools surface is
  unlisted: search the exact term `tools` to open it.
* Step check-state is per-session and never written back.
* Per-file JSON storage; last-write-wins on the rare same-second edit.
* Clean-slate alpha: no data migration. Delete `data\` between builds.
