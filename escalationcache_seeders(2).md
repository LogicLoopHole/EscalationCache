# EscalationCache
### A concept for solving a problem you've probably already felt

---

## The Problem You Already Know

You've been in this situation: something breaks in a way the KB doesn't cover. You remember vaguely that someone fixed it six months ago by doing something weird with a registry key or running a command with a flag nobody documented. You either remember it or you don't. If you don't, you start from scratch or you find that one person who might know — if they're available, if they're not already on something urgent.

That knowledge existed. It just didn't have anywhere to live.

The KB isn't built for this. It's built for formal, polished, approved procedures. It has a one-year delete policy that punishes anyone who writes something informal. There's no incentive to contribute and implied ownership of anything you post. So people don't. They keep it in their heads, their personal OneNotes, or a Teams message that'll be unreadable in six months.

EscalationCache is built specifically for the stuff that falls through those gaps.

---

## What It Actually Is

A shared knowledge layer for T2 and T3. Fast, rough, useful entries. No ownership, just contributors. Built to be easy to write during or right after an escalation, not as a separate documentation task that sits on a to-do list forever.

Think less wiki, more cache. When you hit a problem, you check the cache first. If it's there, great. If it's not, you solve it the way you always have — and then you drop what you figured out into the cache so the next person doesn't start from scratch.

The entries don't need to be polished. They need to be accurate enough to be useful. The format helps, but it doesn't mandate anything.

---

## The Exchange (How It Works)

EscalationCache runs on **Influence** — a measure of contribution to the system. You build it by putting things in. You spend it to use certain tools and to access entries that are getting stale.

*(Working term. Ability Points is the alternative placeholder. Neither is locked — but naming isn't the thing that matters right now.)*

**You build Influence by:**
- Submitting an entry
- Having your entry validated by a peer
- Having your entry cited or used by others over time

**You spend Influence to:**
- Access and run tools built into the system
- Use older entries whose backing hasn't been recently validated (stale cache costs more — keeps things honest)

**New users start with a small amount of Influence** so the system isn't a dead end before you've contributed anything.

**Returning users who've been away a while earn a small amount back** — capped, so it doesn't turn into free access for being inactive.

The cost for a tool adjusts automatically based on how recently its backing documentation was validated. If someone just confirmed it works last week, it's cheap. If it hasn't been touched in six months, it costs more. No manager required — the signal does the work.

---

## Trust Tiers

Not everything is equal. Entries have tags that tell you where they stand:

| Tag | What it means |
|---|---|
| `submitted` | Where every contribution starts — someone put their name on this and shared it |
| `tested` | A named person tested it on a specific date with a specific method |
| `approved` | A relevant stakeholder reviewed it |
| `stale` | Hasn't been validated recently — costs more to use, nudges someone to revalidate |
| `superseded` | Something better exists — this one decays out gracefully |

When an entry goes stale or gets superseded, that's not a reflection on whoever submitted it. Information ages. That's honest. The goal is to make decay visible and cheap to fix, not to punish the person who contributed in the first place.

A `submitted` entry with no other tags is still more useful than knowledge that only exists in one person's head.

Tools in the system have their own tier requirements. Some things anyone can run. Others require a track record of validated contributions before they unlock. The system tracks that automatically — no one has to approve you manually.

---

## Writing Entries: Aids, Not Templates

The entry format doesn't enforce structure. It offers tools:

- **Step builder** — one click to add a numbered step with a checkbox. Good for anything someone will follow along with in the field. Inspired by [i12bretro's tutorial format](https://i12bretro.github.io/tutorials/0001.html) — clean, each step completable in isolation, easy to track progress under pressure.
- **Gotcha flag** — a callout block for the "before you do this" and "this only works if" knowledge that never makes it into formal docs but causes comebacks when it's missing.
- **Tested-on stamp** — fills in your name and today's date for the `tested` tag automatically.

None of these are required. Freeform is fine. The aids are there for when they'd save you time, not to make every entry look the same.

---

## Why You're Seeing This First

This is a concept, not a finished product. Nothing is built yet. The reason this is being shared before anything else is that the design should reflect what people who actually work escalations find useful — not assumptions made in isolation.

This group came to mind first because breakfix is exactly where something like this earns its keep — time is short, info needs to move fast, and the documented path has already failed. Honest feedback on whether this solves a real problem, whether the approach makes sense, and what's missing or overcomplicated is what would actually move this forward.

No commitment implied by reading it.

---

## What Would Help Right Now

This is still at the concept stage, so the most useful feedback is honest reaction — does this solve a real problem, does the approach feel right, and is there anything that seems overcomplicated or missing entirely. If there's something you already know and have wanted to share but didn't have a good place to put it, that's exactly the kind of signal worth surfacing.

Questions about how anything is intended to work are welcome. Nothing here is magic — just a series of observational discoveries by clever people, finally with somewhere to live.

---

*EscalationCache — working concept, seed access only.*
