from fastapi import APIRouter

from ..deps import DB, EntrepreneurUser
from ..models import Profile
from ..schemas import ProfileIn, ProfileOut

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
def get_profile(user: EntrepreneurUser, db: DB):
    return db.get(Profile, user.id) or ProfileOut()


@router.put("", response_model=ProfileOut)
def put_profile(body: ProfileIn, user: EntrepreneurUser, db: DB):
    """Replace the whole profile (fields not sent become empty)."""
    row = db.get(Profile, user.id) or Profile(user_id=user.id)
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    db.add(row)
    db.commit()
    return row
