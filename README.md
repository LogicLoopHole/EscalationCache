# EscalationCache — Alpha (run notes)

The *concept* — what this is and why — lives in the seeders doc. This file only covers
running the alpha and where it intentionally differs from the full idea.

## Run

Windows PowerShell 5.1, in a real console host (**Windows Terminal** or **conhost** — not the ISE):

```powershell
cd escalationcache
powershell -ExecutionPolicy Bypass -File .\EscalationCache.ps1
```

First run creates a `data\` folder beside the scripts, seeds four sample entries and one tool,
and a user record for `%USERNAME%` (5 starting Influence). **Delete `data\` to reset.**
There is no Quit command — close the window or Ctrl+C.

## How it behaves

- **Launch is a search box.** Type words and Enter; type `T` for tools. Search matches *any*
  word across title and body (broad on purpose), then you narrow in the grid.
- Picking a result opens a grid; a confirm box shows the Influence cost before you spend.
- The detail view is interactive: arrows move, Space checks steps off, and the footer keys
  run actions. Validate and Citation Request each ask a Yes/No first.
- Improve opens the editor pre-filled, then previews your text before you title it.

## What's deliberately not here (vs. the concept doc)

- **No login** (identity is `%USERNAME%`) and **no tier gating** — if you can afford a tool, you can run it.
- **Tools are simulated** — running one charges Influence and prints a placeholder; nothing executes.
- **Citation requests are free** (no reward) to avoid farming a one-click action.
- **Aids not built yet:** the gotcha-flag and code-block buttons. Only the check-off step button exists.
- Storage is flat JSON (one file per entry/user/tool; prior versions as `<id>.v<n>.json`). No database.

## Tuning

Everything is in the `$script:Cfg` block at the top of `EscalationCache.ps1`:
`StartingInfluence`, `StaleAfterDays`, `CostCap`, `CostPerDays`, `BaseCost` per tier,
the `ReturnBonus*` settings, and `UseWinFormsEditor = $false` to force the Notepad editor.

## Files

`EscalationCache.ps1` (entry point + flows) · `Influence.ps1` (the economy) ·
`Entries.ps1` (storage + actions) · `UI.ps1` (dialogs, picker, prompts) ·
`Editor.ps1` (body editor) · `Checklist.ps1` (interactive detail/check-off).
The last two are optional — delete either and the app falls back gracefully.
