"""Funding-path optimizer and loan maths.

The path is a *planning illustration* (greedy allocation across eligible / potentially
eligible schemes, then own contribution, then a labelled remaining gap) -- not a
guaranteed approval sequence.
"""
from ..constants import ELIGIBILITY_RANK
from ..models import Scheme
from .eligibility import ProfileSnapshot, classify_scheme, money


# --------------------------------------------------------------------------- EMI
def emi_for(principal: float, rate_pct: float, years: float, moratorium_months: float = 0) -> dict:
    """Standard reducing-balance EMI. Interest is capitalised during a moratorium."""
    rate = (rate_pct or 0) / 1200
    months = (years or 0) * 12
    p = max(0.0, principal)
    if moratorium_months > 0 and rate > 0:
        p = p * (1 + rate) ** moratorium_months
    if rate and months:
        growth = (1 + rate) ** months
        emi = p * rate * growth / (growth - 1)
    else:
        emi = p / months if months else 0.0
    total = emi * months
    return {"principal": p, "emi": emi, "total": total, "interest": max(0.0, total - p)}


# --------------------------------------------------------------------------- funding path
def funding_path(total_needed: float | None, schemes: list[Scheme], profile: ProfileSnapshot) -> dict:
    total = float(total_needed or 0)
    if not total:
        return {"total": 0.0, "steps": [], "gap": 0.0}

    ranked = [(s, classify_scheme(s, profile)) for s in schemes]
    ranked = [(s, c) for s, c in ranked if c.status != "not_eligible"]
    ranked.sort(key=lambda sc: (-ELIGIBILITY_RANK[sc[1].status], -sc[0].max_amount))

    remaining = total
    steps: list[dict] = []
    for s, c in ranked:
        if remaining <= 0:
            break
        amount = min(remaining, s.max_amount)
        if amount <= 0:
            continue
        steps.append({
            "source": "scheme", "scheme_id": s.id, "scheme_name": s.name, "eligibility_status": c.status,
            "amount": round(amount, 2),
            "reason": f"Highest-ranked eligible scheme with a {money(s.max_amount)} limit",
        })
        remaining -= amount

    own = profile.own_contribution or 0
    if remaining > 0 and own > 0:
        amount = min(remaining, own)
        steps.append({
            "source": "own_contribution", "scheme_id": None, "scheme_name": None, "eligibility_status": None,
            "amount": round(amount, 2), "reason": "From your entered margin money / own contribution",
        })
        remaining -= amount

    return {"total": total, "steps": steps, "gap": float(max(0, round(remaining)))}
