from fastapi import APIRouter
from sqlalchemy import select

from ..deps import DB, EntrepreneurUser
from ..models import Application, Document, Profile
from ..schemas import ReadinessOut
from ..services.eligibility import ProfileSnapshot
from ..services.readiness import compute_readiness
from .schemes import all_schemes

router = APIRouter(prefix="/readiness", tags=["readiness"])


@router.get("", response_model=ReadinessOut)
def get_readiness(user: EntrepreneurUser, db: DB):
    """Transparent 100-point readiness score, recomputed live from profile + documents + applications."""
    profile = ProfileSnapshot.from_row(db.get(Profile, user.id))
    uploaded = set(db.scalars(select(Document.document_type).where(Document.user_id == user.id)))
    latest = db.scalar(
        select(Application).where(Application.user_id == user.id)
        .order_by(Application.created_at.desc(), Application.id.desc()).limit(1)
    )
    return compute_readiness(profile, all_schemes(db), uploaded, latest)
