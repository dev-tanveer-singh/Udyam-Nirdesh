import re

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from ..deps import DB, AdminUser, CurrentUser, EntrepreneurUser
from ..models import Application, Partner, Profile, Scheme
from ..schemas import SchemeIn, SchemeMatchOut, SchemeOut
from ..services.eligibility import ProfileSnapshot, rank_schemes

router = APIRouter(prefix="/schemes", tags=["schemes"])


def all_schemes(db) -> list[Scheme]:
    """Stable order (creation order) -- ranking ties are broken by it, exactly like the original list."""
    return list(db.scalars(select(Scheme).order_by(Scheme.created_at, Scheme.id)))


def _unique_slug(db, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50] or "scheme"
    slug, n = base, 2
    while db.get(Scheme, slug):
        slug = f"{base}-{n}"
        n += 1
    return slug


@router.get("", response_model=list[SchemeOut])
def list_schemes(_: CurrentUser, db: DB):
    return all_schemes(db)


# NOTE: declared before "/{scheme_id}" so "matches" is not read as an id.
@router.get("/matches", response_model=list[SchemeMatchOut])
def scheme_matches(user: EntrepreneurUser, db: DB):
    """Every scheme classified against the caller's saved profile, best match first."""
    profile = ProfileSnapshot.from_row(db.get(Profile, user.id))
    return [
        SchemeMatchOut(
            scheme=SchemeOut.model_validate(s),
            eligibility_status=c.status,
            match_pct=c.pct,
            checks=c.items,
        )
        for s, c in rank_schemes(all_schemes(db), profile)
    ]


@router.get("/{scheme_id}", response_model=SchemeOut)
def get_scheme(scheme_id: str, _: CurrentUser, db: DB):
    scheme = db.get(Scheme, scheme_id)
    if not scheme:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scheme not found")
    return scheme


@router.post("", response_model=SchemeOut, status_code=status.HTTP_201_CREATED)
def create_scheme(body: SchemeIn, _: AdminUser, db: DB):
    scheme = Scheme(id=_unique_slug(db, body.name), **body.model_dump())
    db.add(scheme)
    db.commit()
    return scheme


@router.put("/{scheme_id}", response_model=SchemeOut)
def update_scheme(scheme_id: str, body: SchemeIn, _: AdminUser, db: DB):
    scheme = db.get(Scheme, scheme_id)
    if not scheme:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scheme not found")
    for key, value in body.model_dump().items():
        setattr(scheme, key, value)
    db.commit()
    return scheme


@router.delete("/{scheme_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scheme(scheme_id: str, _: AdminUser, db: DB):
    scheme = db.get(Scheme, scheme_id)
    if not scheme:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scheme not found")
    in_use = db.scalar(select(func.count()).select_from(Application).where(Application.scheme_id == scheme_id))
    if in_use:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{in_use} application(s) refer to this scheme, so it cannot be deleted.")
    # keep partners' supported_scheme_ids free of dangling references
    for partner in db.scalars(select(Partner)):
        if scheme_id in (partner.supported_scheme_ids or []):
            partner.supported_scheme_ids = [i for i in partner.supported_scheme_ids if i != scheme_id]
    db.delete(scheme)
    db.commit()
