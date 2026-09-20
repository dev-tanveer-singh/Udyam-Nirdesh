from fastapi import APIRouter

from ..deps import DB, EntrepreneurUser
from ..models import Profile
from ..schemas import EmiIn, EmiOut, FundingPathOut, ScenarioOut, WhatIfIn, WhatIfOut
from ..services.eligibility import ProfileSnapshot, rank_schemes
from ..services.funding import emi_for, funding_path
from .schemes import all_schemes

router = APIRouter(prefix="/tools", tags=["tools"])


@router.post("/emi", response_model=EmiOut)
def emi(body: EmiIn, _: EntrepreneurUser):
    """Loan / EMI calculator (illustrative, not a loan offer)."""
    net = max(0.0, body.loan_amount - body.subsidy - body.own_contribution)
    calc = emi_for(net, body.interest_rate, body.tenure_years, body.moratorium_months)
    return EmiOut(
        net_loan_amount=net, monthly_emi=round(calc["emi"], 2), total_repayment=round(calc["total"], 2),
        total_interest=round(calc["interest"], 2), moratorium_months=body.moratorium_months,
    )


@router.post("/what-if", response_model=WhatIfOut)
def what_if(body: WhatIfIn, user: EntrepreneurUser, db: DB):
    """Compare the saved profile ('current') with a hypothetical funding scenario ('what_if')."""
    profile = ProfileSnapshot.from_row(db.get(Profile, user.id))
    schemes = all_schemes(db)

    def scenario(p: ProfileSnapshot, funding: float, own: float, rate: float, years: float, moratorium: float) -> ScenarioOut:
        loan = max(0.0, funding - own)
        calc = emi_for(loan, rate, years, moratorium)
        ranked = rank_schemes(schemes, p)
        top, cls = ranked[0] if ranked else (None, None)
        return ScenarioOut(
            funding_required=funding, own_contribution=own, loan_portion=loan, interest_rate=rate, tenure_years=years,
            emi=round(calc["emi"], 2), total_repayment=round(calc["total"], 2), funding_gap=max(0.0, funding - own),
            top_scheme_id=top.id if top else None, top_scheme_name=top.name if top else None,
            eligibility_status=cls.status if cls else None,
        )

    return WhatIfOut(
        current=scenario(profile, profile.funding_required or 0, profile.own_contribution or 0, 10, 5, 0),
        what_if=scenario(profile.with_funding(body.funding_required), body.funding_required, body.own_contribution,
                         body.interest_rate, body.tenure_years, body.moratorium_months),
    )


@router.get("/funding-path", response_model=FundingPathOut)
def get_funding_path(user: EntrepreneurUser, db: DB):
    """Funding path for the saved funding requirement. Returns {total: 0, steps: []} if none is saved."""
    profile = ProfileSnapshot.from_row(db.get(Profile, user.id))
    return funding_path(profile.funding_required, all_schemes(db), profile)
