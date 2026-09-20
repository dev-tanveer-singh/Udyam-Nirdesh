from fastapi import APIRouter

from .. import constants as C
from ..schemas import MetaOut

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/meta", response_model=MetaOut)
def meta() -> MetaOut:
    """Reference lists used by the frontend forms and filters (single source of truth)."""
    return MetaOut(
        genders=list(C.GENDERS),
        categories=list(C.CATEGORIES),
        states=list(C.STATES),
        business_types=list(C.BUSINESS_TYPES),
        business_stages=list(C.BUSINESS_STAGES),
        document_types=[{"type": k, "label": v} for k, v in C.DOCUMENT_TYPES.items()],
        application_statuses=[{"value": k, "label": v} for k, v in C.APPLICATION_STATUSES.items()],
    )
