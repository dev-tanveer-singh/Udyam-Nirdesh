from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..deps import DB, CurrentUser
from ..models import User
from ..schemas import LoginIn, RegisterIn, TokenOut, UserOut
from ..security import (
    burn_password_check,
    create_access_token,
    hash_password,
    login_throttle,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: DB):
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "This email is already registered.")
    user = User(
        full_name=body.full_name,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # two simultaneous registrations for the same address
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This email is already registered.")
    return user


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: DB):
    ip = request.client.host if request.client else "unknown"
    if login_throttle.is_blocked(ip, body.email):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed login attempts. Please wait a few minutes and try again.",
            headers={"Retry-After": "300"},
        )

    user = db.scalar(select(User).where(User.email == body.email))
    if user is None:
        burn_password_check(body.password)
        valid = False
    else:
        valid = verify_password(body.password, user.password_hash) and user.is_active

    if not valid:
        login_throttle.record_failure(ip, body.email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")

    login_throttle.clear(ip, body.email)
    token, expires_in = create_access_token(user.id, user.role)
    return TokenOut(access_token=token, expires_in=expires_in, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user
