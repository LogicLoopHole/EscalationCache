"""
store.py - persistence + domain operations.
JSON files on disk (per entry, per user, per tool). Body is plain text with
block markers: [step]...[/step], [code]...[/code], [disclaimer]...[/disclaimer].
No em dashes anywhere in this project, by standing request.
"""
import json, os, re, getpass
from pathlib import Path
from datetime import date, timedelta

import config
from economy import (
    add_influence, get_access_cost, get_display_tag, validate_reward,
    record_access,
)

# ---- Paths -----------------------------------------------------------------
def entries_dir(): return config.DATA_DIR / "entries"
def users_dir():   return config.DATA_DIR / "users"
def tools_dir():   return config.DATA_DIR / "tools"

def _entry_path(eid):  return entries_dir() / f"{int(eid)}.json"
def _user_path(uid):   return users_dir()   / f"{uid}.json"

def _ensure_dirs():
    for d in (entries_dir(), users_dir(), tools_dir()):
        d.mkdir(parents=True, exist_ok=True)


# ---- Atomic JSON I/O -------------------------------------------------------
def read_json(path):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

def write_json(obj, path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)   # atomic on Windows


# ---- Users -----------------------------------------------------------------
def get_user(uid=None, display_name=None):
    if uid is None:
        uid = getpass.getuser()
    if display_name is None:
        display_name = uid
    u = read_json(_user_path(uid))
    if u is None:
        u = {
            "id": uid,
            "display_name": display_name,
            "influence": config.STARTING_INFLUENCE,
            "last_login": None,
            "return_bonus_total": 0,
            "access_log": {},
        }
        write_json(u, _user_path(uid))
    if "access_log" not in u:
        u["access_log"] = {}
    return u

def save_user(user):
    write_json(user, _user_path(user["id"]))


# ---- Counter ---------------------------------------------------------------
def next_entry_id():
    p = config.DATA_DIR / "counters.json"
    c = read_json(p) or {"next_entry_id": 1}
    nid = int(c["next_entry_id"])
    c["next_entry_id"] = nid + 1
    write_json(c, p)
    return nid


# ---- Entries: load / save / list ------------------------------------------
def get_entry(eid):
    return read_json(_entry_path(eid))

def save_entry(entry):
    write_json(entry, _entry_path(entry["id"]))

_NUM_JSON = re.compile(r"^\d+\.json$")
def get_all_entries():
    """Current versions only. Skips .v<n>.json history files."""
    if not entries_dir().exists():
        return []
    out = []
    for f in entries_dir().iterdir():
        if _NUM_JSON.match(f.name):
            e = read_json(f)
            if e is not None:
                out.append(e)
    return out


# ---- Body block syntax -----------------------------------------------------
# A line is a tag line iff it equals exactly "[tag]" or "[/tag]": no leading
# whitespace, no trailing content. Anything else is content. Unknown tags are
# treated as plain text.

BLOCK_TAGS = ("step", "code", "disclaimer")

_OPEN_RE  = re.compile(r"^\[([a-z]+)\]$")
_CLOSE_RE = re.compile(r"^\[/([a-z]+)\]$")

def parse_body(body):
    """
    Yield ("text", str) or (one of BLOCK_TAGS, inner_text) blocks in order.
    Unclosed blocks at EOF emit whatever they accumulated. Tolerant by design.
    """
    body = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = body.split("\n")
    i, n = 0, len(lines)
    text_buf = []

    def flush_text():
        if text_buf:
            joined = "\n".join(text_buf).strip("\n")
            if joined.strip():
                yield ("text", joined)
            text_buf.clear()

    while i < n:
        line = lines[i]
        m_open = _OPEN_RE.match(line)
        if m_open and m_open.group(1) in BLOCK_TAGS:
            yield from flush_text()
            tag = m_open.group(1)
            inner = []
            i += 1
            while i < n:
                m_close = _CLOSE_RE.match(lines[i])
                if m_close and m_close.group(1) == tag:
                    i += 1
                    break
                inner.append(lines[i])
                i += 1
            yield (tag, "\n".join(inner).strip("\n"))
            continue
        text_buf.append(line)
        i += 1
    yield from flush_text()

def serialize_body(blocks):
    out = []
    for kind, content in blocks:
        if kind == "text":
            out.append(content)
        else:
            out.append(f"[{kind}]")
            out.append(content)
            out.append(f"[/{kind}]")
    return "\n\n".join(out)

def search_text(body):
    """Strip tag-syntax lines for search; keep content of every block."""
    return " \n ".join(content for _kind, content in parse_body(body))


# ---- Search ----------------------------------------------------------------
def _entry_corpus(entry):
    """
    Searchable text for an entry: title + current body + every prior version's
    body. This lets a keyword that lived only in an old version still surface
    the contribution, while results always point at the current version.
    """
    parts = [entry.get("title") or "", search_text(entry.get("body") or "")]
    for v in get_prior_versions(entry["id"]):
        parts.append(search_text(v.get("body") or ""))
    return " \n ".join(parts)

def search_entries(term):
    """
    Broad word-match across title + current body + prior-version bodies.
    Ranked by hit count, then title-matches first, then alphabetical.
    Always returns the current version once (no duplicate rows per version).
    """
    t = (term or "").strip()
    if not t:
        return []
    words = [w for w in t.split() if w]
    results = []
    for e in get_all_entries():
        title = e.get("title") or ""
        corpus_lc = _entry_corpus(e).casefold()
        hits = sum(1 for w in words if w.casefold() in corpus_lc)
        if hits == 0:
            continue
        title_lc = title.casefold()
        in_title = any(w.casefold() in title_lc for w in words)
        results.append({
            "id": int(e["id"]),
            "title": title,
            "where": "title" if in_title else "body",
            "hits": hits,
        })
    results.sort(key=lambda r: (-r["hits"], r["where"] != "title", r["title"].casefold()))
    return results


# ---- Validations helpers ---------------------------------------------------
def get_validations(entry):
    return list(entry.get("validations") or [])


# ---- The contribution actions ---------------------------------------------
def new_entry(title, body, user):
    eid = next_entry_id()
    today = date.today().isoformat()
    e = {
        "id": eid,
        "title": title,
        "body": body,
        "tag": "submitted",
        "cited_by": None,
        "cited_date": None,
        "version": 1,
        "created_by": user["display_name"],
        "created": today,
        "author": user["display_name"],   # author = current-version author (last improver)
        "updated": today,                  # updated = last improve date
        "validations": [],
    }
    save_entry(e)
    add_influence(user, config.EARN_PIONEER)
    record_access(user, eid)   # pioneer: free to reopen/edit for the window
    return e

def update_entry(entry, title, body, user):
    """Improve: archive the current version, then overwrite. Trust resets to
    submitted, version bumps, citation clears. Creator/created are preserved."""
    ver_path = entries_dir() / f"{int(entry['id'])}.v{int(entry['version'])}.json"
    write_json(entry, ver_path)
    entry["title"] = title
    entry["body"] = body
    entry["tag"] = "submitted"        # trust resets on improvement
    entry["cited_by"] = None          # citation resolved by the improvement
    entry["cited_date"] = None
    entry["version"] = int(entry["version"]) + 1
    entry["author"] = user["display_name"]      # last improver
    entry["updated"] = date.today().isoformat() # improve date
    entry["validations"] = []
    entry.setdefault("created_by", entry["author"])
    entry.setdefault("created", entry["updated"])
    save_entry(entry)
    add_influence(user, config.EARN_IMPROVE)
    return entry

def confirm_entry(entry, user):
    """
    Validate: additive vouch. Sets the green 'validated' tag, clears any open
    citation (resolution by vouching), and rewards on an age + flag scale.
    Does NOT bump the version or change the improve date: the body is unchanged.
    Returns None if this user already validated this version.
    """
    vals = get_validations(entry)
    if any(v.get("by") == user["display_name"] for v in vals):
        return None
    reward = validate_reward(entry)          # compute before clearing the flag
    today = date.today().isoformat()
    vals.append({"by": user["display_name"], "date": today})
    entry["validations"] = vals
    entry["tag"] = "validated"
    entry["cited_by"] = None
    entry["cited_date"] = None
    save_entry(entry)
    add_influence(user, reward)
    return entry, reward

def set_citation(entry, user):
    """Free flag; no influence reward, to avoid farming."""
    entry["cited_by"] = user["display_name"]
    entry["cited_date"] = date.today().isoformat()
    save_entry(entry)
    return entry

def clear_citation(entry):
    entry["cited_by"] = None
    entry["cited_date"] = None
    save_entry(entry)
    return entry


# ---- Version history -------------------------------------------------------
_VERS_RE = re.compile(r"^(\d+)\.v(\d+)\.json$")
def get_prior_versions(eid):
    if not entries_dir().exists():
        return []
    eid = int(eid)
    out = []
    for f in entries_dir().iterdir():
        m = _VERS_RE.match(f.name)
        if m and int(m.group(1)) == eid:
            v = read_json(f)
            if v is not None:
                out.append(v)
    out.sort(key=lambda v: int(v.get("version", 0)))
    return out


# ---- Tools -----------------------------------------------------------------
def get_tools():
    if not tools_dir().exists():
        return []
    out = []
    for f in tools_dir().iterdir():
        if f.suffix == ".json":
            t = read_json(f)
            if t is not None:
                out.append(t)
    return out


# ---- Seed data (first run only) -------------------------------------------
def _ago(n):
    return (date.today() - timedelta(days=n)).isoformat()

def _seed():
    """Create the sample entries + one tool on first run. Clean-slate alpha:
    delete the data folder to reseed."""
    _ensure_dirs()
    if get_all_entries():
        return

    # SCCM: improved to v2 (so it demos the Improved column), validated long
    # ago (so it displays stale), and currently flagged. Its v1 history holds
    # a keyword ('ccmsetup') dropped in v2, to demo cross-version search.
    sccm_v1 = {
        "id": 1,
        "title": "SCCM app deployment fails silently on VPN",
        "body":
            "[step]\nCheck ccmsetup.log for the silent exit code\n[/step]\n\n"
            "[step]\nDisconnect VPN before initiating deployment\n[/step]\n\n"
            "[step]\nRun deployment from Software Center manually\n[/step]",
        "tag": "submitted", "cited_by": None, "cited_date": None,
        "version": 1, "created_by": "J. Park", "created": _ago(560),
        "author": "J. Park", "updated": _ago(560), "validations": [],
    }
    write_json(sccm_v1, entries_dir() / "1.v1.json")

    sccm_v2 = {
        "id": 1,
        "title": "SCCM app deployment fails silently on VPN",
        "body":
            "[step]\nDisconnect VPN before initiating deployment\n[/step]\n\n"
            "[step]\nRun deployment from Software Center manually\n[/step]\n\n"
            "[step]\nReconnect VPN once installation reaches downloading state\n[/step]\n\n"
            "[step]\nIf still failing, run the repair command below\n[/step]\n\n"
            "[code]\nccmrepair.exe\n[/code]",
        "tag": "validated", "cited_by": "R. Vasquez", "cited_date": _ago(20),
        "version": 2, "created_by": "J. Park", "created": _ago(560),
        "author": "K. Marsh", "updated": _ago(500),
        "validations": [{"by": "K. Marsh", "date": _ago(500)}],
    }

    outlook = {
        "id": 2,
        "title": "Outlook search empty after mailbox migration",
        "body":
            "[step]\nOpen Indexing Options\n[/step]\n\n"
            "[step]\nRemove and re-add the Outlook data store\n[/step]\n\n"
            "[step]\nAllow the index to rebuild\n[/step]\n\n"
            "[step]\nRestart Outlook\n[/step]\n\n"
            "[disclaimer]\nThe user has to stay on corp wifi until the index reports complete, otherwise it stalls and you have to start over.\n[/disclaimer]",
        "tag": "validated", "cited_by": None, "cited_date": None,
        "version": 1, "created_by": "D. Okafor", "created": _ago(95),
        "author": "D. Okafor", "updated": _ago(95),
        "validations": [{"by": "D. Okafor", "date": _ago(80)}],
    }

    teams = {
        "id": 3,
        "title": "Teams audio drops on docked Surface devices",
        "body":
            "[step]\nSet dock as default comms device\n[/step]\n\n"
            "[step]\nPin dock audio in Teams devices\n[/step]\n\n"
            "[step]\nDisable exclusive control for dock audio\n[/step]",
        "tag": "submitted", "cited_by": None, "cited_date": None,
        "version": 1, "created_by": "R. Vasquez", "created": _ago(8),
        "author": "R. Vasquez", "updated": _ago(8), "validations": [],
    }

    printer = {
        "id": 4,
        "title": "Printer spooler crash after KB5034441",
        "body":
            "[step]\nStop the spooler\n[/step]\n\n"
            "[code]\nnet stop spooler\n[/code]\n\n"
            "[step]\nClear the PRINTERS spool folder\n[/step]\n\n"
            "[step]\nReinstall affected printer drivers\n[/step]\n\n"
            "[step]\nStart the spooler\n[/step]\n\n"
            "[code]\nnet start spooler\n[/code]",
        "tag": "validated", "cited_by": None, "cited_date": None,
        "version": 1, "created_by": "T. Nguyen", "created": _ago(410),
        "author": "T. Nguyen", "updated": _ago(410),
        "validations": [{"by": "T. Nguyen", "date": _ago(400)}],
    }

    for e in (sccm_v2, outlook, teams, printer):
        save_entry(e)
    write_json({"next_entry_id": 5}, config.DATA_DIR / "counters.json")
    write_json(
        {
            "id": "app-installer",
            "name": "App Installer (SCCM wrapper)",
            "description": "Placeholder for the real PSADT-invoking executor; alpha simulates the run.",
            "access_cost_base": 3,
            "backing_entry_id": 1,
        },
        tools_dir() / "app-installer.json",
    )


def init():
    """Called once at app startup. Ensures dirs and seeds first-run data."""
    _ensure_dirs()
    _seed()
