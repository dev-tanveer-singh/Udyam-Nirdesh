"""Funding Readiness Score -- transparent 100-point breakdown:
Eligibility 30 / Documents 20 / Financial 20 / Business & project 20 / Application 10.

Recomputed on every request from the live profile, uploaded documents and applications,
using the same checks as the scheme matcher (single source of truth).
"""
from ..constants import DOCUMENT_TYPES, PRE_SUBMISSION_STATUSES
from ..models import Application, Scheme
from .eligibility import ProfileSnapshot, chk, classify_scheme, money, rank_schemes, round_half_up


def _score(items: list[dict], max_score: int) -> int:
    return round_half_up(sum(i["status"] == "ok" for i in items) / (len(items) or 1) * max_score)


def compute_readiness(
    profile: ProfileSnapshot,
    schemes: list[Scheme],
    uploaded_types: set[str],
    latest_application: Application | None,
) -> dict:
    p = profile
    ranked = rank_schemes(schemes, p)
    top, top_cls = ranked[0] if ranked else (None, None)
    categories: list[dict] = []

    # 1. Eligibility match -- 30 pts, straight from the matcher's checks for the top scheme
    elig = top_cls.items if top_cls else []
    per_check = 30 / len(elig) if elig else 0
    categories.append({
        "key": "eligibility", "label": "Eligibility Match", "max_score": 30,
        "score": round_half_up(sum(i["status"] == "ok" for i in elig) * per_check),
        "items": elig,
    })

    # 2. Document readiness -- 20 pts, against the top scheme's required docs (or the full checklist)
    required = list(top.required_documents) if top else list(DOCUMENT_TYPES)
    doc_items = []
    for slug in required:
        label = DOCUMENT_TYPES.get(slug, slug)
        doc_items.append(
            chk("ok", f"{label} uploaded") if slug in uploaded_types
            else chk("bad", f"{label} missing", f"Upload {label}")
        )
    categories.append({
        "key": "documents", "label": "Document Readiness", "max_score": 20,
        "score": round_half_up(sum(i["status"] == "ok" for i in doc_items) / (len(required) or 1) * 20),
        "items": doc_items,
    })

    # 3. Financial readiness -- 20 pts
    fin = []
    fin.append(chk("ok", "Annual income provided") if (p.annual_income or 0) > 0
               else chk("warn", "Income not entered", "Enter your annual income in Profile"))
    fin.append(chk("ok", "Turnover/financial baseline provided")
               if (p.annual_turnover or 0) > 0 or p.business_stage in ("Idea", "New Business")
               else chk("warn", "Turnover not entered", "Enter your annual turnover in Profile"))
    if p.funding_required is None:
        fin.append(chk("warn", "Funding requirement not entered", "Enter your funding requirement in Profile"))
    elif top and not (top.min_amount <= p.funding_required <= top.max_amount):
        fin.append(chk("bad", f"Funding requirement is outside {top.name}\u2019s range",
                       "Adjust funding requirement or review other schemes"))
    else:
        fin.append(chk("ok", "Project amount within scheme limit"))

    needed_pct = top.own_contribution_pct if top else 0.10
    if p.funding_required is None:
        fin.append(chk("warn", "Own contribution not assessed (enter funding first)", "Enter your funding requirement in Profile"))
    elif p.own_contribution is None and needed_pct > 0:
        fin.append(chk("warn", "Own contribution not entered", "Enter your own contribution (margin money) in Profile"))
    else:
        actual_pct = (p.own_contribution or 0) / (p.funding_required or 1)
        if actual_pct >= needed_pct:
            fin.append(chk("ok", f"Own contribution covers the typical {round_half_up(needed_pct * 100)}% margin-money norm"))
        else:
            fin.append(chk("bad",
                           f"Own contribution may be insufficient (currently ~{round_half_up(actual_pct * 100)}% of funding, "
                           f"typically ~{round_half_up(needed_pct * 100)}% expected)",
                           "Increase own contribution or reduce funding requested"))
    categories.append({"key": "financial", "label": "Financial Readiness", "max_score": 20,
                       "score": _score(fin, 20), "items": fin})

    # 4. Business / project readiness -- 20 pts
    biz = [
        chk("ok", "Business type specified") if p.business_type else chk("warn", "Business type not entered", "Enter your business type in Profile"),
        chk("ok", "Business stage specified") if p.business_stage else chk("warn", "Business stage not entered", "Enter your business stage in Profile"),
        chk("ok", "Funding purpose described") if p.funding_purpose else chk("warn", "Funding purpose not entered", "Enter your funding purpose in Profile"),
        chk("ok", "Project report uploaded") if "project_report" in uploaded_types else chk("bad", "Project report missing", "Upload your Project Report"),
    ]
    categories.append({"key": "business", "label": "Business & Project Readiness", "max_score": 20,
                       "score": _score(biz, 20), "items": biz})

    # 5. Application completeness -- 10 pts
    submitted = latest_application is not None and latest_application.status not in PRE_SUBMISSION_STATUSES
    app_items = [
        chk("ok", "An application has been started") if latest_application
        else chk("warn", "No application started yet", "Add an application from the Applications page"),
        chk("ok", "Application submitted to the official portal") if submitted
        else chk("warn", "Application not yet submitted", "Submit your application on the official portal, then update its status here"),
    ]
    categories.append({"key": "application", "label": "Application Completeness", "max_score": 10,
                       "score": _score(app_items, 10), "items": app_items})

    all_items = [{**i, "category": c["label"]} for c in categories for i in c["items"]]
    return {
        "overall": sum(c["score"] for c in categories),
        "top_scheme": None if not top else {
            "scheme_id": top.id, "name": top.name, "description": top.description,
            "eligibility_status": top_cls.status, "match_pct": top_cls.pct,
        },
        "categories": categories,
        "strengths": [i for i in all_items if i["status"] == "ok"],
        "gaps": [i for i in all_items if i["status"] != "ok"],
    }


__all__ = ["compute_readiness", "money", "classify_scheme"]
