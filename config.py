"""
config.py - tunable constants for EscalationCache.
Edit numbers here to retune the economy; nothing else should need to change.
No em dashes anywhere in this project, by standing request.
"""
from pathlib import Path

# ---- App identity ----------------------------------------------------------
APP_TITLE = "EscalationCache Alpha Test v0.2.4"

# ---- Storage ---------------------------------------------------------------
# Data folder lives next to the scripts so the whole thing is portable
# (drop the folder anywhere on the UNC and it just works).
DATA_DIR = Path(__file__).parent / "data"

# ---- Economy: starting + return --------------------------------------------
STARTING_INFLUENCE     = 5
RETURN_BONUS           = 1     # +1 on login after RETURN_BONUS_IDLE_DAYS away
RETURN_BONUS_IDLE_DAYS = 7
RETURN_BONUS_CAP       = 10    # lifetime cap on accumulated return bonuses

# ---- Cost formula ----------------------------------------------------------
# access_cost = min(COST_CAP, max(1, base_for_display_tag + (days_since_validation // COST_PER_DAYS)))
COST_CAP         = 8
COST_PER_DAYS    = 60
STALE_AFTER_DAYS = 180   # validated entries older than this display as 'stale' (computed, never stored)

BASE_COST = {
    "submitted": 1,
    "validated": 2,
    "stale":     3,   # display-only tag; pushes base up so old fixes cost more
}

# ---- Free access window ----------------------------------------------------
# Once you pay to open a contribution it stays free to reopen for this long.
# Tools are excluded. The clock does not reset on reopen (24h from first pay).
FREE_WINDOW_HOURS = 24

# ---- Earn: contribution actions --------------------------------------------
EARN_PIONEER  = 3
EARN_IMPROVE  = 3
EARN_CITATION = 0   # free by design: one-click flag, no farm incentive

# ---- Earn: validation (scales with age, bonus for resolving a flag) --------
# reward = min(VALIDATE_CAP, VALIDATE_BASE + days_since_validation // VALIDATE_AGE_DIVISOR)
#          + (VALIDATE_CITATION_BONUS if the contribution is flagged)
# Self-validation (validating a version you authored) is blocked entirely.
VALIDATE_BASE           = 1
VALIDATE_AGE_DIVISOR    = 30   # one extra influence per month of staleness
VALIDATE_CAP            = 8    # cap on base+age; citation bonus stacks on top
VALIDATE_CITATION_BONUS = 2    # extra for validating a flagged contribution
