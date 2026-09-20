from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from ..deps import DB, AdminUser, CurrentUser
from ..models import Partner, Scheme
from ..schemas import PartnerIn, PartnerOut
from ..services.geo import haversine_km

router = APIRouter(prefix="/partners", tags=["partners"])


def _all(db) -> list[Partner]:
    return list(db.scalars(select(Partner).order_by(Partner.created_at, Partner.name)))


@router.get("", response_model=list[PartnerOut])
def list_partners(
    _: CurrentUser,
    db: DB,
    q: str = "",
    state: str | None = None,
    district: str | None = None,
    scheme_id: str | None = None,
):
    """Filter the directory. A state filter also returns pan-India partners (state = null)."""
    needle = q.strip().lower()
    out = []
    for p in _all(db):
        haystack = " ".join([p.name, p.partner_type, p.coverage, p.notes, p.district or "", p.state or "", *p.supported_scheme_ids]).lower()
        if needle and needle not in haystack:
            continue
        if state and state != "All States" and p.state not in (None, state):
            continue
        if district and (p.district or "").lower() != district.strip().lower():
            continue
        if scheme_id and scheme_id not in p.supported_scheme_ids:
            continue
        out.append(p)
    return out


@router.get("/nearby", response_model=list[PartnerOut])
def nearby_partners(
    _: CurrentUser,
    db: DB,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
    radius_km: Annotated[float, Query(gt=0, le=2000)] = 100,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    include_national: bool = True,
):
    """Geospatial locator: partners with coordinates inside `radius_km`, nearest first.
    Pan-India partners (no coordinates) are appended afterwards, without a distance."""
    located, national = [], []
    for p in _all(db):
        if p.latitude is None or p.longitude is None:
            if p.state is None:
                national.append(p)
            continue
        d = haversine_km(lat, lng, p.latitude, p.longitude)
        if d <= radius_km:
            out = PartnerOut.model_validate(p)
            out.distance_km = round(d, 1)
            located.append(out)
    located.sort(key=lambda x: x.distance_km)
    result = located[:limit]
    if include_national:
        result += [PartnerOut.model_validate(p) for p in national][: max(0, limit - len(result))]
    return result


@router.post("", response_model=PartnerOut, status_code=status.HTTP_201_CREATED)
def create_partner(body: PartnerIn, _: AdminUser, db: DB):
    known = set(db.scalars(select(Scheme.id)))
    unknown = [i for i in body.supported_scheme_ids if i not in known]
    if unknown:
        raise HTTPException(422, f"Unknown supported_scheme_ids: {', '.join(unknown)}")
    partner = Partner(**body.model_dump())
    db.add(partner)
    db.commit()
    return partner


@router.delete("/{partner_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_partner(partner_id: str, _: AdminUser, db: DB):
    partner = db.get(Partner, partner_id)
    if not partner:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Partner not found")
    db.delete(partner)
    db.commit()
