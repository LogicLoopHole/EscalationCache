"""
MIT License

Copyright (c) 2026 LogicLoopHole

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

economy.py - the Influence economy. Isolated so the formula is easy to find and tune.

Depends on: config (constants), store.save_user (called by add/use).
The save_user import is deferred to avoid a cycle.
"""
from datetime import date, datetime
import config


def _today():
    return date.today()


def _now():
    return datetime.now()


def _parse_date(s):
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


# ---- Validation date logic -------------------------------------------------
# Validations are an additive list of {by, date} on each entry. The relevant
# date for cost/stale is the most recent one.

def get_last_validation_date(entry):
    dates = []
    for v in entry.get("validations") or []:
        d = _parse_date(v.get("date"))
        if d:
            dates.append(d)
    return max(dates) if dates else None


def get_days_since_validation(entry):
    d = get_last_validation_date(entry)
    return None if d is None else (_today() - d).days


def is_stale(entry):
    d = get_days_since_validation(entry)
    return d is not None and d >= config.STALE_AFTER_DAYS


def get_display_tag(entry):
    """The tag the user sees. 'stale' is computed here, never stored."""
    tag = entry.get("tag")
    if get_last_validation_date(entry) is None:
        return tag          # 'submitted' - never validated yet
    if is_stale(entry):
        return "stale"
    return tag              # 'validated'


# ---- Cost ------------------------------------------------------------------

def get_access_cost(entry):
    """min(cap, max(1, base_for_display_tag + days_since // per))."""
    base = config.BASE_COST.get(get_display_tag(entry), 1)
    days = get_days_since_validation(entry) or 0
    cost = base + (days // config.COST_PER_DAYS)
    return max(1, min(config.COST_CAP, cost))


def get_tool_cost(tool, entry_lookup):
    """Tool cost mirrors entry cost, tied to the tool's backing entry age."""
    base = int(tool.get("access_cost_base", 1))
    days = 0
    backing_id = tool.get("backing_entry_id")
    if backing_id is not None:
        backing = entry_lookup(int(backing_id))
        if backing is not None:
            d = get_days_since_validation(backing)
            if d is not None:
                days = d
    cost = base + (days // config.COST_PER_DAYS)
    return max(1, min(config.COST_CAP, cost))


# ---- Validation reward -----------------------------------------------------

def validate_reward(entry):
    """
    Reward for validating someone else's contribution.
    Base + age scaling (older = more, to refresh stale knowledge), plus a flat
    bonus if the contribution is currently flagged (prioritises flagged work).
    Call this BEFORE clearing the citation so the bonus is counted.
    """
    days = get_days_since_validation(entry)
    if days is None:
        created = _parse_date(entry.get("created") or entry.get("updated"))
        days = 0 if created is None else (_today() - created).days
    age_part = config.VALIDATE_BASE + (days // config.VALIDATE_AGE_DIVISOR)
    age_part = min(config.VALIDATE_CAP, age_part)
    bonus = config.VALIDATE_CITATION_BONUS if entry.get("cited_by") else 0
    return age_part + bonus


# ---- Free access window ----------------------------------------------------
# Per-user access log: {str(entry_id): iso datetime of last paid open}.

def is_free_access(user, entry_id):
    ts = (user.get("access_log") or {}).get(str(entry_id))
    if not ts:
        return False
    try:
        then = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return False
    return (_now() - then).total_seconds() < config.FREE_WINDOW_HOURS * 3600


def free_hours_remaining(user, entry_id):
    """Whole hours left in the free window, or None if not active."""
    ts = (user.get("access_log") or {}).get(str(entry_id))
    if not ts:
        return None
    try:
        then = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    remaining = config.FREE_WINDOW_HOURS * 3600 - (_now() - then).total_seconds()
    if remaining <= 0:
        return None
    # round up so a window with 30 minutes left still reads as "1h", never "0h"
    import math
    return max(1, math.ceil(remaining / 3600.0))


def effective_cost(user, entry):
    """0 if inside the free window, else the normal access cost."""
    if is_free_access(user, entry["id"]):
        return 0
    return get_access_cost(entry)


def record_access(user, entry_id):
    """Stamp a paid open. Starts (or, after expiry, restarts) the free window."""
    from store import save_user
    log = user.get("access_log") or {}
    log[str(entry_id)] = _now().isoformat()
    user["access_log"] = log
    save_user(user)


# ---- Earn / spend ----------------------------------------------------------

def add_influence(user, amount):
    from store import save_user
    user["influence"] = int(user.get("influence", 0)) + int(amount)
    save_user(user)
    return user["influence"]


def use_influence(user, amount):
    from store import save_user
    bal = int(user.get("influence", 0))
    if bal < amount:
        return False
    user["influence"] = bal - int(amount)
    save_user(user)
    return True


# ---- Return bonus ----------------------------------------------------------

def grant_return_bonus(user):
    from store import save_user
    granted = 0
    last = _parse_date(user.get("last_login"))
    if last is not None:
        idle = (_today() - last).days
        acc = int(user.get("return_bonus_total", 0))
        if idle >= config.RETURN_BONUS_IDLE_DAYS and acc < config.RETURN_BONUS_CAP:
            granted = config.RETURN_BONUS
            user["influence"] = int(user.get("influence", 0)) + granted
            user["return_bonus_total"] = acc + granted
    user["last_login"] = _today().isoformat()
    save_user(user)
    return granted
