from fastapi import APIRouter
from sqlalchemy import select

from ..deps import DB, AdminUser
from ..models import User
from ..schemas import UserOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
def list_users(_: AdminUser, db: DB):
    return db.scalars(select(User).order_by(User.created_at, User.email)).all()
