"""Rule-based scheme matching -- a transparent checklist, not a credit decision.

Ported 1:1 from the original frontend `classifyScheme()` so scores do not change when the
logic moves to the server. Every check returns {status, text, action}:
  ok   requirement satisfied (counts toward the score)
  warn information missing -> cannot confirm either way (0 points, non-blocking)
  bad  requirement actively fails (0 points, blocking)
"""
import math
from dataclasses import dataclass, replace

from ..constants import ELIGIBILITY_RANK
from ..models import Profile, Scheme


def round_half_up(x: float) -> int:
    """JavaScript's Math.round (Python's round() is banker's rounding and would differ on .5)."""
    return math.floor(x + 0.5)


def inr(n: float) -> str:
    """Indian digit grouping: 1234567 -> 12,34,567."""
    s = str(int(round(n)))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


def money(n: float) -> str:
    return "\u20b9" + inr(n or 0)


@dataclass(frozen=True)
class ProfileSnapshot:
    """Plain copy of the profile fields the engine reads (lets us run 'what-if' without touching the DB)."""
    age: int | None = None
    category: str | None = None
    business_type: str | None = None
    business_stage: str | None = None
    annual_income: float | None = None
    annual_turnover: float | None = None
    funding_required: float | None = None
    own_contribution: float | None = None
    funding_purpose: str | None = None

    @classmethod
    def from_row(cls, row: Profile | None) -> "ProfileSnapshot":
        if row is None:
            return cls()
        return cls(**{f: getattr(row, f) for f in cls.__dataclass_fields__})

    def with_funding(self, funding_required: float) -> "ProfileSnapshot":
        return replace(self, funding_required=funding_required)


def chk(status: str, text: str, action: str | None = None) -> dict:
    return {"status": status, "text": text, "action": action}


@dataclass
class Classification:
    status: str          # eligible | potentially_eligible | not_eligible
    pct: int
    items: list[dict]


def classify_scheme(s: Scheme, p: ProfileSnapshot) -> Classification:
    items: list[dict] = []

    # Category
    if p.category and p.category in s.eligible_categories:
        items.append(chk("ok", f'Category "{p.category}" is eligible for this scheme'))
    elif p.category:
        items.append(chk("bad", f'Category "{p.category}" is not listed for this scheme',
                         "Review category-specific rules or choose another scheme"))
    else:
        items.append(chk("warn", "Social category not entered", "Enter your social category in Profile"))

    # Business type
    if p.business_type and p.business_type in s.business_types:
        items.append(chk("ok", f'Business type "{p.business_type}" fits this scheme'))
    elif p.business_type:
        items.append(chk("bad", f'Business type "{p.business_type}" is not covered by this scheme',
                         "Choose a scheme that covers your business type"))
    else:
        items.append(chk("warn", "Business type not entered", "Enter your business type in Profile"))

    # Business stage
    if p.business_stage and p.business_stage in s.business_stages:
        items.append(chk("ok", f'Business stage "{p.business_stage}" matches'))
    elif p.business_stage:
        items.append(chk("bad", f'Business stage "{p.business_stage}" is not covered by this scheme',
                         "Choose a scheme for your current stage"))
    else:
        items.append(chk("warn", "Business stage not entered", "Enter your business stage in Profile"))

    # Age
    min_age = s.min_age or 18
    if p.age is not None:
        if p.age >= min_age:
            items.append(chk("ok", "Age requirement is met"))
        else:
            items.append(chk("bad", f"Applicant must be at least {min_age} years old",
                             "This scheme is not applicable below the minimum age"))
    else:
        items.append(chk("warn", "Age not entered", "Enter your age in Profile"))

    # Income limit
    if s.max_income is None:
        items.append(chk("ok", "No personal income limit applies to this scheme"))
    elif p.annual_income is None:
        items.append(chk("warn", "Income not entered", "Enter your annual income in Profile"))
    elif p.annual_income <= s.max_income:
        items.append(chk("ok", "Income eligibility satisfied"))
    else:
        items.append(chk("bad", f"Income exceeds this scheme\u2019s {money(s.max_income)} limit",
                         "Review income eligibility or choose another scheme"))

    # Funding within the scheme's limits
    if p.funding_required is None:
        items.append(chk("warn", "Funding requirement not entered", "Enter your funding requirement in Profile"))
    elif s.min_amount <= p.funding_required <= s.max_amount:
        items.append(chk("ok", f"Project amount is within this scheme\u2019s {money(s.min_amount)}\u2013{money(s.max_amount)} limit"))
    else:
        items.append(chk("bad", f"Funding requirement is outside this scheme\u2019s {money(s.min_amount)}\u2013{money(s.max_amount)} range",
                         "Adjust the funding requirement or choose another scheme"))

    bad = sum(i["status"] == "bad" for i in items)
    warn = sum(i["status"] == "warn" for i in items)
    ok = sum(i["status"] == "ok" for i in items)
    status = "not_eligible" if bad else "potentially_eligible" if warn else "eligible"
    return Classification(status=status, pct=round_half_up(ok / len(items) * 100), items=items)


def rank_schemes(schemes: list[Scheme], p: ProfileSnapshot) -> list[tuple[Scheme, Classification]]:
    """Best first: eligibility status, then % of checks passed. Stable, like the original sort."""
    scored = [(s, classify_scheme(s, p)) for s in schemes]
    scored.sort(key=lambda sc: (-ELIGIBILITY_RANK[sc[1].status], -sc[1].pct))
    return scored
